"""对话式 Agent 端点测试 (WP3)。

覆盖: 对话轮次 (后台执行 + 助手消息落库)、404、执行失败时错误信息落库。
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1.endpoints.agent_chat import _final_answer
from app.models.execution import Execution, ExecutionStatus


# ── 辅助函数 ──

async def _register_and_login(client, email="chat@test.com", password="secret123"):
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "Chat User", "password": password,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_llm(monkeypatch):
    async def fake_chat(messages, model="default", user=None, **kwargs):
        last = messages[-1]["content"] if messages else ""
        return f"LLM回复: {last[:50]}"
    monkeypatch.setattr("app.services.execution_service.llm_chat", fake_chat)


@pytest.fixture
def patch_session_factory(db_engine, monkeypatch):
    """同时 patch run_flow 用的工厂与 agent_chat 模块内已导入的工厂引用。"""
    import app.core.database as db_module

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    monkeypatch.setattr("app.api.v1.endpoints.agent_chat.async_session_factory", factory)
    return factory


async def _wait_assistant_message(
    client, flow_id, token, conversation_id=None, timeout_s=10.0
):
    """轮询消息列表直到出现助手消息。"""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        params = {"conversation_id": conversation_id} if conversation_id else None
        resp = await client.get(
            f"/api/v1/agent-flows/{flow_id}/chat/messages",
            params=params,
            headers=_auth_headers(token),
        )
        assert resp.status_code == 200
        messages = resp.json()
        assistants = [m for m in messages if m["role"] == "assistant"]
        if assistants:
            return messages, assistants[-1]
        await asyncio.sleep(0.2)
    raise AssertionError("超时未等到助手消息")


# ── 测试 ──

@pytest.mark.asyncio
async def test_chat_roundtrip(client, db_engine, patch_session_factory, mock_llm):
    """一轮对话: 用户消息落库 → 后台执行工作流 → 助手回答落库。"""
    token = await _register_and_login(client)

    dag = {
        "nodes": [
            {"id": "n1", "type": "text", "position": {"x": 0, "y": 0},
             "data": {"label": "输入", "config": {"template": "问题: {input}"}}},
            {"id": "n2", "type": "llm", "position": {"x": 300, "y": 0},
             "data": {"label": "LLM", "config": {
                 "model": "default", "system_prompt": "你是助手", "user_template": "{n1}"}}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "ChatFlow", "dag": dag,
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/chat",
        json={"message": "你好"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 202
    assert "execution_id" in resp.json()
    assert "conversation_id" in resp.json()

    messages, answer = await _wait_assistant_message(client, flow_id, token)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "你好"
    assert "LLM回复" in answer["content"]
    assert "问题: 你好" in answer["content"]


@pytest.mark.asyncio
async def test_conversation_create_switch_and_delete(
    client, db_engine, patch_session_factory, mock_llm
):
    """多个会话分别保存消息，切换不串历史，删除后消息也不可访问。"""
    token = await _register_and_login(client, "chat-multi@test.com")
    create_flow = await client.post(
        "/api/v1/agent-flows",
        json={"name": "Multi chat", "dag": {"nodes": [], "edges": []}},
        headers=_auth_headers(token),
    )
    flow_id = create_flow.json()["id"]

    initial = await client.get(
        f"/api/v1/agent-flows/{flow_id}/chat/conversations",
        headers=_auth_headers(token),
    )
    assert initial.status_code == 200
    assert len(initial.json()) == 1
    initial_id = initial.json()[0]["id"]

    created = await client.post(
        f"/api/v1/agent-flows/{flow_id}/chat/conversations",
        headers=_auth_headers(token),
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    sent = await client.post(
        f"/api/v1/agent-flows/{flow_id}/chat",
        json={"message": "第二个会话", "conversation_id": conversation_id},
        headers=_auth_headers(token),
    )
    assert sent.status_code == 202
    assert sent.json()["conversation_id"] == conversation_id
    messages, _ = await _wait_assistant_message(
        client, flow_id, token, conversation_id=conversation_id
    )
    assert messages[0]["content"] == "第二个会话"

    empty = await client.get(
        f"/api/v1/agent-flows/{flow_id}/chat/messages",
        params={"conversation_id": initial_id},
        headers=_auth_headers(token),
    )
    assert empty.status_code == 200
    assert empty.json() == []

    conversations = await client.get(
        f"/api/v1/agent-flows/{flow_id}/chat/conversations",
        headers=_auth_headers(token),
    )
    titled = {item["id"]: item["title"] for item in conversations.json()}
    assert titled[conversation_id] == "第二个会话"

    deleted = await client.delete(
        f"/api/v1/agent-flows/{flow_id}/chat/conversations/{conversation_id}",
        headers=_auth_headers(token),
    )
    assert deleted.status_code == 204
    missing = await client.get(
        f"/api/v1/agent-flows/{flow_id}/chat/messages",
        params={"conversation_id": conversation_id},
        headers=_auth_headers(token),
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_conversation_endpoints_enforce_flow_ownership(client):
    owner_token = await _register_and_login(client, "chat-owner@test.com")
    other_token = await _register_and_login(client, "chat-other@test.com")
    flow = await client.post(
        "/api/v1/agent-flows",
        json={"name": "Private chat", "dag": {"nodes": [], "edges": []}},
        headers=_auth_headers(owner_token),
    )
    flow_id = flow.json()["id"]
    conversations = await client.get(
        f"/api/v1/agent-flows/{flow_id}/chat/conversations",
        headers=_auth_headers(owner_token),
    )
    conversation_id = conversations.json()[0]["id"]

    assert (
        await client.get(
            f"/api/v1/agent-flows/{flow_id}/chat/conversations",
            headers=_auth_headers(other_token),
        )
    ).status_code == 404
    assert (
        await client.delete(
            f"/api/v1/agent-flows/{flow_id}/chat/conversations/{conversation_id}",
            headers=_auth_headers(other_token),
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_chat_flow_not_found(client):
    token = await _register_and_login(client, "chat404@test.com")
    resp = await client.post(
        "/api/v1/agent-flows/00000000-0000-0000-0000-000000000000/chat",
        json={"message": "hi"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_failed_flow_saves_error(client, db_engine, patch_session_factory, mock_llm):
    """工作流执行失败 (DAG 循环依赖) 时, 错误信息作为助手消息落库而不是静默丢失。"""
    token = await _register_and_login(client, "chatfail@test.com")

    dag = {
        "nodes": [
            {"id": "n1", "type": "text", "position": {"x": 0, "y": 0},
             "data": {"label": "A", "config": {"template": "a"}}},
            {"id": "n2", "type": "text", "position": {"x": 300, "y": 0},
             "data": {"label": "B", "config": {"template": "b"}}},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n1"},
        ],
    }
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "CycleFlow", "dag": dag,
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/chat",
        json={"message": "hi"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 202

    _, answer = await _wait_assistant_message(client, flow_id, token)
    assert "循环依赖" in answer["content"]


def test_final_answer_does_not_mask_failure_or_cancellation_with_partial_output():
    """失败或取消时必须展示终态原因，不能误把最后一个成功节点当作回答。"""
    failed = Execution(
        status=ExecutionStatus.failed,
        output={"partial": "看似成功的中间结果"},
        node_states={"partial": {"status": "success", "output": "中间结果"}},
        error_message="模型供应商不可用",
    )
    cancelled = Execution(
        status=ExecutionStatus.cancelled,
        output={"partial": "中间结果"},
        node_states={},
    )

    assert _final_answer(failed) == "模型供应商不可用"
    assert _final_answer(cancelled) == "(执行已取消)"
