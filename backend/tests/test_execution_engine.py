"""执行引擎单元测试 (WP3)。

覆盖: 启动前取消 / 运行中取消 / 节点重试(指数退避) / 环检测 /
多 case 条件裁剪补 skipped / HTTP 节点 (mock httpx) / retrieval 节点 KB owner 校验 /
node_states duration_ms。

DB 用 SQLite 内存库; run_flow 内部的 async_session_factory 通过 monkeypatch 指向测试库。
"""

import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.agent_flow import AgentFlow
from app.models.execution import Execution, ExecutionStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.push_channel import ChannelType, PushChannel
from app.models.user import User
from app.services import execution_service
from app.utils.crypto import encrypt


# ── 辅助函数 ──

async def _make_user(db, email="engine@test.com"):
    user = User(email=email, name="Engine", hashed_password="x")
    db.add(user)
    await db.commit()
    return user


async def _make_flow(db, owner_id, dag):
    flow = AgentFlow(name="EngineFlow", owner_id=owner_id, dag=dag)
    db.add(flow)
    await db.commit()
    return flow


async def _make_execution(db, flow_id, input_data=None):
    ex = Execution(flow_id=flow_id, status=ExecutionStatus.pending, input=input_data or {"input": "你好"})
    db.add(ex)
    await db.commit()
    return ex


@pytest.fixture
def patch_session_factory(db_engine, monkeypatch):
    """把引擎内部使用的 async_session_factory 指向测试库。"""
    import app.core.database as db_module

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", factory)
    return factory


@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLM 调用。"""
    async def fake_chat(messages, model="default", user=None, **kwargs):
        last = messages[-1]["content"] if messages else ""
        return f"LLM回复: {last[:50]}"
    monkeypatch.setattr("app.services.execution_service.llm_chat", fake_chat)
    return fake_chat


def _text_node(nid, label, template):
    return {"id": nid, "type": "text", "position": {"x": 0, "y": 0},
            "data": {"label": label, "config": {"template": template}}}


def _notify_node(channel_ids):
    return {
        "id": "notify-1",
        "type": "notify",
        "position": {"x": 0, "y": 0},
        "data": {
            "label": "通知",
            "config": {
                "channel_ids": channel_ids,
                "title_template": "完成",
                "content_template": "结果: {input}",
            },
        },
    }


@pytest.mark.asyncio
async def test_notify_node_resolves_owner_channel(
    db_session, patch_session_factory, monkeypatch
):
    """工作流只存 channel id，执行时按 owner 解密并发送。"""
    user = await _make_user(db_session, "notify-owner@test.com")
    channel = PushChannel(
        owner_id=user.id,
        name="团队通知",
        type=ChannelType.telegram,
        config={"bot_token": encrypt("123:secret"), "chat_id": "9988"},
    )
    db_session.add(channel)
    await db_session.commit()

    flow = await _make_flow(
        db_session,
        user.id,
        {"nodes": [_notify_node([str(channel.id)])], "edges": []},
    )
    execution = await _make_execution(db_session, flow.id, {"input": "日报"})
    sent = []

    async def fake_notify(channels, title, content):
        sent.extend(channels)
        assert title == "完成"
        assert content == "结果: 日报"
        return [{"channel": "telegram", "success": True, "error": None}]

    monkeypatch.setattr("app.core.notify_client.notify", fake_notify)
    await execution_service.run_flow(execution.id, flow.id)

    await db_session.refresh(execution)
    assert execution.status == ExecutionStatus.success
    assert sent == [{"bot_token": "123:secret", "chat_id": "9988", "type": "telegram"}]
    assert execution.node_states["notify-1"]["output"] == "推送完成: 1/1 渠道成功"


@pytest.mark.asyncio
async def test_notify_node_rejects_foreign_channel(
    db_session, patch_session_factory, monkeypatch
):
    """引用其他 owner 的渠道时执行失败，且不会调用发送器。"""
    owner = await _make_user(db_session, "flow-owner@test.com")
    other = await _make_user(db_session, "channel-owner@test.com")
    channel = PushChannel(
        owner_id=other.id,
        name="foreign",
        type=ChannelType.hermes,
        config={"channel": "ops"},
    )
    db_session.add(channel)
    await db_session.commit()

    flow = await _make_flow(
        db_session,
        owner.id,
        {"nodes": [_notify_node([str(channel.id)])], "edges": []},
    )
    execution = await _make_execution(db_session, flow.id)
    sent = []

    async def fake_notify(*args):
        sent.append(args)
        return []

    monkeypatch.setattr("app.core.notify_client.notify", fake_notify)
    await execution_service.run_flow(execution.id, flow.id)

    await db_session.refresh(execution)
    assert execution.status == ExecutionStatus.failed
    assert "不存在或无权访问" in execution.node_states["notify-1"]["error"]
    assert sent == []


# ── P0-2: 启动前取消 ──

@pytest.mark.asyncio
async def test_cancel_before_start(db_session, patch_session_factory, mock_llm):
    """pending 期被取消的执行, run_flow 启动时直接退出, 不执行任何节点。"""
    user = await _make_user(db_session)
    dag = {"nodes": [_text_node("n1", "T", "hello")], "edges": []}
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id)

    ok = await execution_service.cancel_execution(db_session, ex.id)
    assert ok is True

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.cancelled
    assert not ex.node_states  # 任何节点都未执行


# ── P0-1: 运行中取消 ──

@pytest.mark.asyncio
async def test_cancel_while_running(db_session, patch_session_factory, mock_llm, monkeypatch):
    """运行中被取消: 节点让出控制权后立即检出并终止, 最终状态保持 cancelled 不被覆写为 success。"""
    user = await _make_user(db_session)
    dag = {
        "nodes": [
            {"id": "n1", "type": "llm", "position": {"x": 0, "y": 0},
             "data": {"label": "LLM", "config": {"model": "default", "user_template": "{input}"}}},
            _text_node("n2", "T2", "不应执行"),
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id)

    # n1 执行期间把执行记录置为 cancelled
    async def cancelling_chat(messages, model="default", user=None, **kwargs):
        async with patch_session_factory() as s:
            target = await s.get(Execution, ex.id)
            target.status = ExecutionStatus.cancelled
            await s.commit()
        return "ok"

    monkeypatch.setattr("app.services.execution_service.llm_chat", cancelling_chat)

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.cancelled  # 未被覆写为 success
    states = ex.node_states or {}
    # 取消在 n1 执行期间到达 → n1 让出控制权后立即标记 cancelled (deploy 语义)
    assert states["n1"]["status"] == "cancelled"
    assert "duration_ms" in states["n1"]
    assert "n2" not in states  # 后续节点未执行


# ── P1-3: 节点重试 (指数退避) ──

@pytest.mark.asyncio
async def test_node_retry_success(db_session, patch_session_factory, monkeypatch):
    """config.retry=2 时, 前两次失败后第三次成功, 整体 success。"""
    user = await _make_user(db_session)
    dag = {
        "nodes": [
            {"id": "n1", "type": "llm", "position": {"x": 0, "y": 0},
             "data": {"label": "LLM", "config": {
                 "model": "default", "user_template": "{input}",
                 "retry": 2, "retry_interval": 0.01,
             }}},
        ],
        "edges": [],
    }
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id)

    calls = []

    async def flaky_chat(messages, model="default", user=None, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("临时故障")
        return "重试后成功"

    monkeypatch.setattr("app.services.execution_service.llm_chat", flaky_chat)

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.success
    assert len(calls) == 3
    assert ex.node_states["n1"]["output"] == "重试后成功"
    assert isinstance(ex.node_states["n1"]["duration_ms"], int)


@pytest.mark.asyncio
async def test_node_retry_exhausted(db_session, patch_session_factory, monkeypatch):
    """重试次数耗尽后节点 failed, 执行 failed。"""
    user = await _make_user(db_session)
    dag = {
        "nodes": [
            {"id": "n1", "type": "llm", "position": {"x": 0, "y": 0},
             "data": {"label": "LLM", "config": {
                 "model": "default", "user_template": "{input}",
                 "retry": 1, "retry_interval": 0.01,
             }}},
        ],
        "edges": [],
    }
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id)

    calls = []

    async def always_fail(messages, model="default", user=None, **kwargs):
        calls.append(1)
        raise RuntimeError("持续故障")

    monkeypatch.setattr("app.services.execution_service.llm_chat", always_fail)

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.failed
    assert len(calls) == 2  # 1 次原始 + 1 次重试
    assert ex.node_states["n1"]["status"] == "failed"
    assert "持续故障" in ex.node_states["n1"]["error"]
    assert "duration_ms" in ex.node_states["n1"]


# ── 环检测 ──

@pytest.mark.asyncio
async def test_cycle_detection(db_session, patch_session_factory, mock_llm):
    """DAG 存在循环依赖时执行 failed 并给出错误信息。"""
    user = await _make_user(db_session)
    dag = {
        "nodes": [_text_node("n1", "A", "a"), _text_node("n2", "B", "b")],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "target": "n1"},
        ],
    }
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id)

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.failed
    assert "循环依赖" in (ex.error_message or "")


# ── P2-6: 多 case 条件裁剪补 skipped ──

@pytest.mark.asyncio
async def test_condition_cases_pruning_marks_skipped(db_session, patch_session_factory, mock_llm):
    """多 case 条件节点: 未命中分支的下游节点标记为 skipped, 命中分支正常执行。"""
    user = await _make_user(db_session)
    dag = {
        "nodes": [
            _text_node("n1", "输入", "是"),
            {"id": "n2", "type": "condition", "position": {"x": 0, "y": 0},
             "data": {"label": "条件", "config": {"cases": [
                 {"id": "c1", "name": "是", "expression": "{n1} == '是'"},
                 {"id": "c2", "name": "否", "expression": "{n1} == '否'"},
             ]}}},
            _text_node("nA", "分支A", "走了A"),
            _text_node("nB", "分支B", "走了B"),
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2"},
            {"id": "e2", "source": "n2", "sourceHandle": "c1", "target": "nA"},
            {"id": "e3", "source": "n2", "sourceHandle": "c2", "target": "nB"},
        ],
    }
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id)

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.success
    states = ex.node_states
    assert states["n2"]["matched_case"] == "c1"
    assert states["nA"]["status"] == "success"
    assert states["nA"]["output"] == "走了A"
    assert states["nB"]["status"] == "skipped"  # 被裁剪分支补 skipped
    assert "duration_ms" in states["nA"]


# ── 契约2: HTTP 节点 (mock httpx) ──

class _FakeResponse:
    def __init__(self, text="OK", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _make_fake_client(calls, queue):
    """生成一个假冒的 httpx.AsyncClient 类: 记录请求, 按队列返回响应/抛异常。"""
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            calls.append({"timeout": kwargs.get("timeout")})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, **kwargs):
            calls.append({"method": method, "url": url, "headers": headers, **kwargs})
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    return FakeAsyncClient


@pytest.mark.asyncio
async def test_http_node_success(db_session, patch_session_factory, monkeypatch):
    """HTTP 节点: 模板渲染 url/headers/body, 响应文本写入 context 供下游引用。"""
    user = await _make_user(db_session)
    dag = {
        "nodes": [
            {"id": "n1", "type": "http", "position": {"x": 0, "y": 0},
             "data": {"label": "API", "config": {
                 "method": "POST",
                 "url": "https://api.example.com/echo?q={input}",
                 "headers": {"X-Token": "t-{input}"},
                 "body": '{"q": "{input}"}',
                 "timeout_s": 5,
             }}},
            _text_node("n2", "下游", "结果={n1}"),
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id, {"input": "你好"})

    calls = []
    queue = [_FakeResponse('{"echo": "pong"}')]
    monkeypatch.setattr(
        execution_service, "assert_url_is_safe", lambda _url: ("api.example.com", "1.1.1.1")
    )
    monkeypatch.setattr(execution_service, "pin_dns_global", lambda *_args: nullcontext())
    monkeypatch.setattr(
        execution_service.httpx, "AsyncClient", _make_fake_client(calls, queue)
    )

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.success
    req = calls[1]
    assert req["method"] == "POST"
    assert req["url"] == "https://api.example.com/echo?q=你好"
    assert req["headers"] == {"X-Token": "t-你好"}
    assert req["json"] == {"q": "你好"}
    assert calls[0]["timeout"] == 5.0
    assert ex.node_states["n1"]["status"] == "success"
    assert "pong" in ex.node_states["n1"]["output"]
    assert "duration_ms" in ex.node_states["n1"]
    # 下游可通过 {n1} 引用 HTTP 响应
    assert ex.node_states["n2"]["output"] == '结果={"echo": "pong"}'


@pytest.mark.asyncio
async def test_http_node_retry_on_error(db_session, patch_session_factory, monkeypatch):
    """HTTP 节点请求异常时按 retry 配置重试, 第二次成功。"""
    user = await _make_user(db_session)
    dag = {
        "nodes": [
            {"id": "n1", "type": "http", "position": {"x": 0, "y": 0},
             "data": {"label": "API", "config": {
                 "method": "GET", "url": "https://api.example.com/flaky",
                 "retry": 1, "retry_interval": 0.01,
             }}},
        ],
        "edges": [],
    }
    flow = await _make_flow(db_session, user.id, dag)
    ex = await _make_execution(db_session, flow.id)

    calls = []
    queue = [ConnectionError("连接失败"), _FakeResponse("RECOVERED")]
    monkeypatch.setattr(
        execution_service, "assert_url_is_safe", lambda _url: ("api.example.com", "1.1.1.1")
    )
    monkeypatch.setattr(execution_service, "pin_dns_global", lambda *_args: nullcontext())
    monkeypatch.setattr(
        execution_service.httpx, "AsyncClient", _make_fake_client(calls, queue)
    )

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.success
    assert len([c for c in calls if c.get("method")]) == 2
    assert ex.node_states["n1"]["output"] == "RECOVERED"


@pytest.mark.asyncio
async def test_http_node_blocks_private_network_before_request(monkeypatch):
    """用户配置的 HTTP 节点不能访问 loopback、内网或云元数据地址。"""
    called = False

    class UnexpectedClient:
        def __init__(self, *args, **kwargs):
            nonlocal called
            called = True

    monkeypatch.setattr(execution_service.httpx, "AsyncClient", UnexpectedClient)

    with pytest.raises(ValueError, match="non-public"):
        await execution_service._execute_http_node(
            {"method": "GET", "url": "http://127.0.0.1:8000/api/v1/health"}, {}
        )

    assert called is False


@pytest.mark.asyncio
async def test_http_node_error_does_not_expose_url_credentials(monkeypatch):
    """HTTP 状态错误只包含状态码，不能把 query token 写入执行错误和日志。"""
    token = "query-secret-token"
    calls = []
    queue = [_FakeResponse("denied", status_code=401)]
    monkeypatch.setattr(
        execution_service, "assert_url_is_safe", lambda _url: ("api.example.com", "1.1.1.1")
    )
    monkeypatch.setattr(execution_service, "pin_dns_global", lambda *_args: nullcontext())
    monkeypatch.setattr(
        execution_service.httpx, "AsyncClient", _make_fake_client(calls, queue)
    )

    with pytest.raises(RuntimeError) as exc_info:
        await execution_service._execute_http_node(
            {"method": "GET", "url": f"https://api.example.com/data?token={token}"}, {}
        )

    assert str(exc_info.value) == "HTTP request returned 401"
    assert token not in str(exc_info.value)


# ── P1-4: retrieval 节点 KB owner 校验 ──

@pytest.mark.asyncio
async def test_retrieval_node_rejects_other_users_kb(db_session, patch_session_factory, mock_llm):
    """retrieval 节点引用他人知识库时节点失败 (KB.owner != flow.owner)。"""
    owner = await _make_user(db_session, "owner@test.com")
    other = await _make_user(db_session, "other@test.com")
    kb = KnowledgeBase(name="私有库", owner_id=other.id)
    db_session.add(kb)
    await db_session.commit()

    dag = {
        "nodes": [
            {"id": "n1", "type": "retrieval", "position": {"x": 0, "y": 0},
             "data": {"label": "检索", "config": {"kb_id": str(kb.id), "query_template": "{input}"}}},
        ],
        "edges": [],
    }
    flow = await _make_flow(db_session, owner.id, dag)
    ex = await _make_execution(db_session, flow.id)

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.failed
    assert "无权访问" in (ex.error_message or "")


@pytest.mark.asyncio
async def test_retrieval_node_own_kb(db_session, patch_session_factory, monkeypatch):
    """retrieval 节点引用本人知识库时正常检索 (mock document_service.search)。"""
    owner = await _make_user(db_session, "owner2@test.com")
    kb = KnowledgeBase(name="我的库", owner_id=owner.id)
    db_session.add(kb)
    await db_session.commit()

    async def fake_search(db, kb_id, request):
        return SimpleNamespace(hits=[SimpleNamespace(content="命中内容")])

    monkeypatch.setattr("app.services.document_service.search", fake_search)

    dag = {
        "nodes": [
            {"id": "n1", "type": "retrieval", "position": {"x": 0, "y": 0},
             "data": {"label": "检索", "config": {"kb_id": str(kb.id), "query_template": "{input}"}}},
        ],
        "edges": [],
    }
    flow = await _make_flow(db_session, owner.id, dag)
    ex = await _make_execution(db_session, flow.id)

    await execution_service.run_flow(ex.id, flow.id)

    await db_session.refresh(ex)
    assert ex.status == ExecutionStatus.success
    assert "命中内容" in ex.node_states["n1"]["output"]
