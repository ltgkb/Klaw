"""M4 模块测试: 记忆系统 + 推送 + 供应商 + 重排序 + 定时任务。

DB 层用 SQLite 内存库 (conftest.py)。外部服务通过 monkeypatch mock。
"""

import pytest


# ── 辅助函数 ──

async def _register_and_login(client, email="m4user@test.com", password="secret123"):
    """注册并登录, 返回 access_token。"""
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "M4 User", "password": password,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── 记忆系统测试 ──

@pytest.mark.asyncio
async def test_memory_crud(client):
    """测试记忆 CRUD。"""
    token = await _register_and_login(client, "mem@test.com")
    h = _auth_headers(token)

    # 创建
    resp = await client.post("/api/v1/memories", json={
        "type": "preference",
        "key": "language",
        "value": {"value": "中文"},
    }, headers=h)
    assert resp.status_code == 201
    mem_id = resp.json()["id"]
    assert resp.json()["key"] == "language"

    # 获取
    resp = await client.get(f"/api/v1/memories/{mem_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["value"]["value"] == "中文"

    # 列表
    resp = await client.get("/api/v1/memories", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 更新
    resp = await client.put(f"/api/v1/memories/{mem_id}", json={
        "value": {"value": "English"},
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["value"]["value"] == "English"

    # 搜索 (GET /memories/search?q=)
    resp = await client.get("/api/v1/memories/search",
        params={"q": "language"}, headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 删除
    resp = await client.delete(f"/api/v1/memories/{mem_id}", headers=h)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/memories/{mem_id}", headers=h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_memory_owner_isolation(client):
    """测试记忆 owner 隔离。"""
    token_a = await _register_and_login(client, "mema@test.com")
    token_b = await _register_and_login(client, "memb@test.com")

    resp = await client.post("/api/v1/memories", json={
        "key": "secret", "value": {"value": "A's data"},
    }, headers=_auth_headers(token_a))
    mem_id = resp.json()["id"]

    # B 看不到 A 的记忆
    resp = await client.get(f"/api/v1/memories/{mem_id}", headers=_auth_headers(token_b))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_memory_upsert(client):
    """测试同 key 记忆更新 (不重复创建)。"""
    token = await _register_and_login(client, "upsert@test.com")
    h = _auth_headers(token)

    # 第一次创建
    await client.post("/api/v1/memories", json={
        "key": "setting", "value": {"value": "v1"},
    }, headers=h)

    # 同 key 再次创建 → 更新 (save_memory upsert 逻辑)
    resp = await client.post("/api/v1/memories", json={
        "key": "setting", "value": {"value": "v2"},
    }, headers=h)
    assert resp.status_code == 201

    # 列表应该只有 1 条
    resp = await client.get("/api/v1/memories", headers=h)
    assert len(resp.json()) == 1
    assert resp.json()[0]["value"]["value"] == "v2"


@pytest.mark.asyncio
async def test_memory_filter_by_type(client):
    """测试按 type 过滤记忆列表。"""
    token = await _register_and_login(client, "filter@test.com")
    h = _auth_headers(token)

    await client.post("/api/v1/memories", json={
        "type": "preference", "key": "lang", "value": {"v": "zh"},
    }, headers=h)
    await client.post("/api/v1/memories", json={
        "type": "decision", "key": "framework", "value": {"v": "fastapi"},
    }, headers=h)

    # 过滤 preference
    resp = await client.get("/api/v1/memories?type=preference", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["key"] == "lang"

    # 全部
    resp = await client.get("/api/v1/memories", headers=h)
    assert len(resp.json()) == 2


# ── 推送测试 ──

@pytest.fixture
def mock_notify(monkeypatch):
    """Mock 推送客户端 — patch notify_client.notify 源函数。

    notifications.py 顶部 `from app.core.notify_client import notify` 导入后,
    notify 绑定到 notifications 模块命名空间; 同时 notify_client 模块也有该属性。
    两处都 patch 确保覆盖。
    """
    from app.core import notify_client
    from app.api.v1.endpoints import notifications as notif_ep

    async def mock_notify_fn(channels, title, content):
        return [{"channel": ch.get("type", ""), "success": True, "error": None} for ch in channels]

    monkeypatch.setattr(notify_client, "notify", mock_notify_fn)
    monkeypatch.setattr(notif_ep, "notify", mock_notify_fn)


@pytest.mark.asyncio
async def test_notify_send(client, mock_notify):
    """测试推送接口。"""
    token = await _register_and_login(client, "notify@test.com")
    resp = await client.post("/api/v1/notifications/send", json={
        "title": "测试通知",
        "content": "这是一条测试消息",
        "channels": [
            {"type": "feishu", "webhook_url": "https://example.com/webhook"},
            {"type": "telegram", "bot_token": "xxx", "chat_id": "123"},
        ],
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 2
    assert all(r["success"] for r in data["results"])


# ── 供应商测试 ──

@pytest.fixture
def mock_llm_provider(monkeypatch):
    """Mock LLM 供应商 — patch llm_client 模块。"""
    from app.core import llm_client

    async def mock_health():
        return True

    async def mock_chat(messages, model="default", user=None, **kwargs):
        return f"Mock回复: {messages[-1]['content'][:30]}"

    async def mock_list_models():
        return [
            {"id": "default", "provider": "openclaw", "name": "默认模型"},
            {"id": "gpt-4o-mini", "provider": "openai", "name": "GPT-4o mini"},
        ]

    monkeypatch.setattr(llm_client, "health_check", mock_health)
    monkeypatch.setattr(llm_client, "chat", mock_chat)
    monkeypatch.setattr(llm_client, "list_models", mock_list_models)
    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", True)


@pytest.mark.asyncio
async def test_providers_list(client, mock_llm_provider):
    """测试供应商列表。"""
    token = await _register_and_login(client, "prov@test.com")
    resp = await client.get("/api/v1/providers", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    # dev 环境会额外返回 mock 兜底供应商
    assert len(data) >= 4
    names = [p["name"] for p in data]
    assert "openclaw" in names
    assert "hermes" in names
    assert "openai" in names
    assert "anthropic" in names
    # openclaw 应该是 ok (mock_health=True)
    openclaw = next(p for p in data if p["name"] == "openclaw")
    assert openclaw["status"] == "ok"
    assert openclaw["deploy"] == "local"


@pytest.mark.asyncio
async def test_providers_models(client, mock_llm_provider):
    """测试模型列表。"""
    token = await _register_and_login(client, "model@test.com")
    resp = await client.get("/api/v1/providers/models", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_providers_chat(client, mock_llm_provider):
    """测试统一对话。"""
    token = await _register_and_login(client, "chat@test.com")
    resp = await client.post("/api/v1/providers/chat", json={
        "messages": [{"role": "user", "content": "你好"}],
        "model": "default",
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    assert "Mock回复" in resp.json()["content"]


# ── 重排序测试 ──

@pytest.fixture
def mock_reranker(monkeypatch):
    """Mock 重排序客户端。

    document_service.search 内部用 `from app.core.reranker_client import rerank as rerank_docs`
    局部导入, 所以 patch 源模块的 rerank 函数即可生效。
    """
    from app.core import reranker_client

    async def mock_rerank(query, documents, top_k=5, timeout=30.0):
        # 按原始顺序返回, 分数递减
        return [{"index": i, "score": 1.0 - i * 0.1} for i in range(min(top_k, len(documents)))]

    monkeypatch.setattr(reranker_client, "rerank", mock_rerank)


@pytest.fixture
def mock_kb_infra(monkeypatch, db_engine):
    """Mock ES/MinIO/TEI, 使检索测试不依赖外部服务 (复用 test_kb.py mock_infra 模式)。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import app.core.database as db_module

    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    # Mock TEI
    async def mock_embed_query(text, timeout=10.0):
        return [0.1] * 1024

    # Mock ES — 返回多个候选供 rerank 精排
    async def mock_hybrid_search(kb_id, query_vector, query_text, top_k=10, num_candidates=200):
        return [
            {
                "chunk_id": f"mock-chunk-{i}",
                "doc_id": f"mock-doc-{i}",
                "content": f"内容片段 {i}: {query_text}",
                "content_type": "text",
                "page": 0,
                "score": 0.9 - i * 0.1,
                "metadata": {},
            }
            for i in range(min(top_k, 4))
        ]

    monkeypatch.setattr("app.services.document_service.embed_query", mock_embed_query)
    monkeypatch.setattr("app.services.document_service.es_hybrid_search", mock_hybrid_search)


@pytest.mark.asyncio
async def test_rerank_in_search(client, mock_kb_infra, mock_reranker):
    """测试检索结果重排序 (mock ES + reranker)。"""
    token = await _register_and_login(client, "rerank@test.com")

    # 先创建 KB
    resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "重排序测试KB",
    }, headers=_auth_headers(token))
    assert resp.status_code == 201
    kb_id = resp.json()["id"]

    # 搜索 (rerank=True) — mock_kb_infra mock ES, mock_reranker mock reranker
    resp = await client.post(f"/api/v1/knowledge-bases/{kb_id}/search", json={
        "query": "测试查询",
        "top_k": 3,
        "rerank": True,
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    # reranker_score 应该被填充
    assert data["hits"][0].get("rerank_score") is not None


@pytest.mark.asyncio
async def test_search_without_rerank(client, mock_kb_infra):
    """测试不启用重排序的检索 (对比测试)。"""
    token = await _register_and_login(client, "norank@test.com")

    resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "普通检索KB",
    }, headers=_auth_headers(token))
    kb_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/knowledge-bases/{kb_id}/search", json={
        "query": "测试",
        "top_k": 3,
        "rerank": False,
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    # 未启用 rerank → rerank_score 应为 None
    assert data["hits"][0].get("rerank_score") is None


# ── 定时任务测试 ──

@pytest.fixture
def mock_scheduler(monkeypatch):
    """Mock APScheduler (避免测试中真正注册定时任务到 PostgreSQL)。

    scheduler.py 中的 schedule_flow / unschedule_flow / pause_scheduled_job /
    resume_scheduled_job 都是同步函数。schedules.py 通过
    `from app.core import scheduler as scheduler_module` 导入后用 scheduler_module.xxx 调用,
    所以 patch 模块属性即可。
    """
    from datetime import datetime, timezone
    from app.core import scheduler as sched_module

    def mock_schedule_flow(job_id, flow_id, cron, input_data, name):
        return datetime.now(timezone.utc)

    def mock_unschedule_flow(job_id):
        pass

    def mock_pause(job_id):
        pass

    def mock_resume(job_id):
        return datetime.now(timezone.utc)

    def mock_next_run(job_id):
        return datetime(2030, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(sched_module, "schedule_flow", mock_schedule_flow)
    monkeypatch.setattr(sched_module, "unschedule_flow", mock_unschedule_flow)
    monkeypatch.setattr(sched_module, "pause_scheduled_job", mock_pause)
    monkeypatch.setattr(sched_module, "resume_scheduled_job", mock_resume)
    monkeypatch.setattr(sched_module, "get_next_run_time", mock_next_run)


@pytest.mark.asyncio
async def test_schedule_crud(client, mock_scheduler):
    """测试定时任务 CRUD。"""
    token = await _register_and_login(client, "sched@test.com")
    h = _auth_headers(token)

    # 先创建 flow
    resp = await client.post("/api/v1/agent-flows", json={
        "name": "定时测试流程",
    }, headers=h)
    assert resp.status_code == 201
    flow_id = resp.json()["id"]

    # 创建定时任务
    resp = await client.post("/api/v1/schedules", json={
        "flow_id": flow_id,
        "name": "每天9点执行",
        "cron": "0 9 * * *",
        "input": {"key": "val"},
    }, headers=h)
    assert resp.status_code == 201
    sched_id = resp.json()["id"]
    assert resp.json()["cron"] == "0 9 * * *"
    assert resp.json()["name"] == "每天9点执行"

    # 列表
    resp = await client.get("/api/v1/schedules", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["next_run_time"].startswith("2030-01-01")

    # 详情
    resp = await client.get(f"/api/v1/schedules/{sched_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["id"] == sched_id

    # 暂停
    resp = await client.put(f"/api/v1/schedules/{sched_id}", json={
        "status": "paused",
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    # 恢复
    resp = await client.put(f"/api/v1/schedules/{sched_id}", json={
        "status": "active",
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # 删除
    resp = await client.delete(f"/api/v1/schedules/{sched_id}", headers=h)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/schedules/{sched_id}", headers=h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_schedule_owner_isolation(client, mock_scheduler):
    """测试定时任务 owner 隔离。"""
    token_a = await _register_and_login(client, "scheda@test.com")
    token_b = await _register_and_login(client, "schedb@test.com")
    h_a = _auth_headers(token_a)

    # A 创建 flow + schedule
    resp = await client.post("/api/v1/agent-flows", json={"name": "A的流程"}, headers=h_a)
    flow_id = resp.json()["id"]
    resp = await client.post("/api/v1/schedules", json={
        "flow_id": flow_id, "name": "A的任务", "cron": "0 9 * * *",
    }, headers=h_a)
    sched_id = resp.json()["id"]

    # B 看不到 A 的定时任务
    resp = await client.get(f"/api/v1/schedules/{sched_id}", headers=_auth_headers(token_b))
    assert resp.status_code == 404

    # B 的列表为空
    resp = await client.get("/api/v1/schedules", headers=_auth_headers(token_b))
    assert resp.status_code == 200
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_schedule_invalid_flow(client, mock_scheduler):
    """测试为不存在的 flow 创建定时任务 → 404。"""
    token = await _register_and_login(client, "badflow@test.com")
    # 随机 UUID
    resp = await client.post("/api/v1/schedules", json={
        "flow_id": "00000000-0000-0000-0000-000000000000",
        "name": "无效任务",
        "cron": "0 9 * * *",
    }, headers=_auth_headers(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_schedule_rejects_invalid_cron(client, mock_scheduler):
    token = await _register_and_login(client, "badcron@test.com")
    headers = _auth_headers(token)
    flow = (await client.post(
        "/api/v1/agent-flows", json={"name": "Bad Cron"}, headers=headers
    )).json()

    response = await client.post(
        "/api/v1/schedules",
        json={"flow_id": flow["id"], "name": "invalid", "cron": "bad cron"},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_notification_failure_includes_error(monkeypatch):
    from app.core import notify_client

    async def rejected(*args, **kwargs):
        return False

    monkeypatch.setattr(notify_client, "send_hermes", rejected)
    results = await notify_client.notify(
        [{"type": "hermes", "channel": "test"}], "title", "content"
    )
    assert results == [{
        "channel": "hermes",
        "success": False,
        "error": "渠道返回失败状态",
    }]
