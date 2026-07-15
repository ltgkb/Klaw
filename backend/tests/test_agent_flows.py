"""Agent 工作流端点测试。

DB 层用 SQLite 内存库。LLM/检索外部服务通过 monkeypatch mock。
"""

import pytest


# ── 辅助函数 ──

async def _register_and_login(client, email="flowuser@test.com", password="secret123"):
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "Flow User", "password": password,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Mock 外部服务 ──

@pytest.fixture
def mock_llm(monkeypatch):
    """Mock LLM 调用, 使测试不依赖外部 LLM 服务。"""
    async def mock_chat(messages, model="default", user=None, **kwargs):
        # 返回最后一条用户消息的简单回复
        last_msg = messages[-1]["content"] if messages else ""
        return f"LLM回复: {last_msg[:50]}"
    monkeypatch.setattr("app.services.execution_service.llm_chat", mock_chat)


# ── 工作流 CRUD 测试 ──

@pytest.mark.asyncio
async def test_create_flow(client):
    token = await _register_and_login(client)
    resp = await client.post("/api/v1/agent-flows", json={
        "name": "测试工作流",
        "description": "用于测试",
    }, headers=_auth_headers(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试工作流"
    assert data["status"] == "draft"
    assert data["dag"] == {"nodes": [], "edges": []}
    assert "id" in data


@pytest.mark.asyncio
async def test_create_flow_unauthorized(client):
    resp = await client.post("/api/v1/agent-flows", json={"name": "test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_flows(client):
    token = await _register_and_login(client)
    for i in range(3):
        await client.post("/api/v1/agent-flows", json={
            "name": f"Flow-{i}",
        }, headers=_auth_headers(token))

    resp = await client.get("/api/v1/agent-flows", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_get_flow(client):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "GetTest",
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/agent-flows/{flow_id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "GetTest"


@pytest.mark.asyncio
async def test_get_flow_not_found(client):
    token = await _register_and_login(client)
    resp = await client.get(
        "/api/v1/agent-flows/00000000-0000-0000-0000-000000000000",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_flow_dag(client):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "DAGTest",
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    dag = {
        "nodes": [
            {"id": "n1", "type": "text", "position": {"x": 0, "y": 0},
             "data": {"label": "输入", "config": {"template": "Hello {input}"}}},
            {"id": "n2", "type": "llm", "position": {"x": 300, "y": 0},
             "data": {"label": "LLM", "config": {"model": "default", "system_prompt": "", "user_template": "{n1}"}}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    resp = await client.put(f"/api/v1/agent-flows/{flow_id}", json={"dag": dag}, headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["dag"]["nodes"][0]["id"] == "n1"
    assert resp.json()["dag"]["edges"][0]["source"] == "n1"


@pytest.mark.asyncio
async def test_delete_flow(client):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "ToDelete",
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/agent-flows/{flow_id}", headers=_auth_headers(token))
    assert resp.status_code == 204

    resp2 = await client.get(f"/api/v1/agent-flows/{flow_id}", headers=_auth_headers(token))
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_flow_owner_isolation(client):
    token_a = await _register_and_login(client, "userA@test.com")
    token_b = await _register_and_login(client, "userB@test.com")

    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "A's Flow",
    }, headers=_auth_headers(token_a))
    flow_id = create_resp.json()["id"]

    # B 看不到 A 的工作流
    resp = await client.get(f"/api/v1/agent-flows/{flow_id}", headers=_auth_headers(token_b))
    assert resp.status_code == 404


# ── 执行测试 ──

@pytest.mark.asyncio
async def test_execute_flow_text_only(client, mock_llm, db_engine, monkeypatch):
    """测试纯文本+LLM节点的执行管线。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import app.core.database as db_module
    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    token = await _register_and_login(client)

    # 创建工作流: 输入 → LLM
    dag = {
        "nodes": [
            {"id": "n1", "type": "text", "position": {"x": 0, "y": 0},
             "data": {"label": "输入", "config": {"template": "问题: {input}"}}},
            {"id": "n2", "type": "llm", "position": {"x": 300, "y": 0},
             "data": {"label": "LLM", "config": {
                 "model": "default",
                 "system_prompt": "你是助手",
                 "user_template": "{n1}",
             }}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "ExecTest", "dag": dag,
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    # 执行
    exec_resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/execute",
        json={"input": {"input": "你好"}},
        headers=_auth_headers(token),
    )
    assert exec_resp.status_code == 201
    execution_id = exec_resp.json()["execution_id"]

    # 检查执行状态 (BackgroundTasks 在 TestClient 中同步完成)
    detail_resp = await client.get(
        f"/api/v1/agent-flows/{flow_id}/executions/{execution_id}",
        headers=_auth_headers(token),
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "success"
    assert detail["node_states"]["n1"]["status"] == "success"
    assert detail["node_states"]["n2"]["status"] == "success"
    assert "问题: 你好" in detail["node_states"]["n1"]["output"]


@pytest.mark.asyncio
async def test_execute_flow_condition(client, mock_llm, db_engine, monkeypatch):
    """测试条件节点执行。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import app.core.database as db_module
    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    token = await _register_and_login(client)

    dag = {
        "nodes": [
            {"id": "n1", "type": "text", "position": {"x": 0, "y": 0},
             "data": {"label": "输入", "config": {"template": "是"}}},
            {"id": "n2", "type": "condition", "position": {"x": 300, "y": 0},
             "data": {"label": "条件", "config": {"expression": "{n1} == '是'"}}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "CondTest", "dag": dag,
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    exec_resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/execute",
        json={"input": {}},
        headers=_auth_headers(token),
    )
    execution_id = exec_resp.json()["execution_id"]

    detail_resp = await client.get(
        f"/api/v1/agent-flows/{flow_id}/executions/{execution_id}",
        headers=_auth_headers(token),
    )
    detail = detail_resp.json()
    assert detail["status"] == "success"
    assert detail["node_states"]["n2"]["output"] == "true"


@pytest.mark.asyncio
async def test_list_executions(client, mock_llm, db_engine, monkeypatch):
    """测试执行历史列表。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import app.core.database as db_module
    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "HistTest",
        "dag": {"nodes": [{"id": "n1", "type": "text", "position": {"x": 0, "y": 0},
                           "data": {"label": "T", "config": {"template": "hello"}}}], "edges": []},
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    # 执行两次
    for _ in range(2):
        await client.post(f"/api/v1/agent-flows/{flow_id}/execute", json={"input": {}}, headers=_auth_headers(token))

    resp = await client.get(f"/api/v1/agent-flows/{flow_id}/executions", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_execute_empty_flow(client, db_engine, monkeypatch):
    """测试空工作流执行 (无节点)。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import app.core.database as db_module
    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/agent-flows", json={
        "name": "Empty",
    }, headers=_auth_headers(token))
    flow_id = create_resp.json()["id"]

    exec_resp = await client.post(
        f"/api/v1/agent-flows/{flow_id}/execute",
        json={"input": {}},
        headers=_auth_headers(token),
    )
    execution_id = exec_resp.json()["execution_id"]

    detail_resp = await client.get(
        f"/api/v1/agent-flows/{flow_id}/executions/{execution_id}",
        headers=_auth_headers(token),
    )
    detail = detail_resp.json()
    assert detail["status"] == "success"
