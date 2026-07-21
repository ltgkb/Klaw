"""新增接口测试: 本地工具发现 / 文件工作区 / 推送渠道配置。"""

import pytest

from tests.test_m4 import _auth_headers, _register_and_login


@pytest.mark.asyncio
async def test_health_checks_configured_embedding_api(monkeypatch):
    from app.api.v1.endpoints import health
    from app.core import embedding_config, tei_client

    monkeypatch.setattr(embedding_config, "is_configured", lambda: True)
    monkeypatch.setattr(
        embedding_config,
        "get",
        lambda: {"base_url": "https://embedding.test/v1", "api_key": "key", "model": "model"},
    )

    async def healthy_api(texts, base_url, api_key, model, timeout):
        return [[0.0] * 1024]

    monkeypatch.setattr(tei_client, "_embed_via_api", healthy_api)

    status = await health._embedding_health_status()
    assert status == "ok: embedding API"
    assert health._status_is_healthy(status) is True


@pytest.mark.asyncio
async def test_health_rejects_wrong_embedding_dimensions(monkeypatch):
    from app.api.v1.endpoints import health
    from app.core import embedding_config, tei_client

    monkeypatch.setattr(embedding_config, "is_configured", lambda: True)
    monkeypatch.setattr(
        embedding_config,
        "get",
        lambda: {"base_url": "https://embedding.test/v1", "api_key": "key", "model": "model"},
    )

    async def wrong_dimensions(texts, base_url, api_key, model, timeout):
        return [[0.0] * 1536]

    monkeypatch.setattr(tei_client, "_embed_via_api", wrong_dimensions)

    status = await health._embedding_health_status()
    assert status == "error: embedding API returned 1536 dimensions"
    assert health._status_is_healthy(status) is False


@pytest.mark.asyncio
async def test_health_requires_tei_without_embedding_api(monkeypatch):
    from app.api.v1.endpoints import health
    from app.core import embedding_config, tei_client

    monkeypatch.setattr(embedding_config, "is_configured", lambda: False)

    async def unhealthy_tei():
        return False

    monkeypatch.setattr(tei_client, "health_check", unhealthy_tei)

    status = await health._embedding_health_status()
    assert status == "error: unhealthy"
    assert health._status_is_healthy(status) is False


# ── 本地工具发现 ──

@pytest.mark.asyncio
async def test_local_agent_tools_discovery(client):
    """测试本地 Skills 发现 (扫描 deploy/*/skills/skill.json)。"""
    token = await _register_and_login(client, "tools@test.com")
    resp = await client.get("/api/v1/local-agent/tools", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    ids = [t["id"] for t in data]
    # deploy/openclaw/skills 下应有 web_search / send_notification
    assert "web_search" in ids
    assert "send_notification" in ids
    # deploy/hermes/skills 下应有 data_analysis
    assert "data_analysis" in ids


@pytest.mark.asyncio
async def test_local_agent_tool_call_mock(client):
    """离线工具调用必须明确失败，不能把 mock 结果报告为执行成功。"""
    token = await _register_and_login(client, "toolcall@test.com")
    resp = await client.post(
        "/api/v1/local-agent/tools/web_search/call",
        json={"parameters": {"query": "hello"}},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    if data["source"] == "mock":
        assert data["success"] is False
        assert data["error"]
        assert data["result"]["mock"] is True
    else:
        assert data["source"] == "openclaw"
        assert data["success"] is True


@pytest.mark.asyncio
async def test_local_agent_health(client):
    """测试本地 Agent 健康检查。"""
    token = await _register_and_login(client, "lh@test.com")
    resp = await client.get("/api/v1/local-agent/health", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "openclaw" in data
    assert "hermes" in data


# ── 推送渠道配置 ──

@pytest.mark.asyncio
async def test_push_channel_crud(client):
    """测试推送渠道配置 CRUD。"""
    token = await _register_and_login(client, "pc@test.com")
    h = _auth_headers(token)

    # 创建
    resp = await client.post("/api/v1/push/channels", json={
        "name": "我的飞书群",
        "type": "feishu",
        "config": {"webhook_url": "https://example.com/webhook"},
    }, headers=h)
    assert resp.status_code == 201
    ch_id = resp.json()["id"]
    # 敏感字段应脱敏
    assert resp.json()["config"]["webhook_url"] == "******"

    # 列表
    resp = await client.get("/api/v1/push/channels", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 删除
    resp = await client.delete(f"/api/v1/push/channels/{ch_id}", headers=h)
    assert resp.status_code == 204

    resp = await client.get("/api/v1/push/channels", headers=h)
    assert len(resp.json()) == 0


@pytest.mark.asyncio
async def test_notify_by_channel_id(client, monkeypatch):
    """测试通过已配置渠道 id 推送 (解密 + 调用, notify 被 mock)。"""
    from app.core import notify_client
    from app.api.v1.endpoints import notifications as notif_ep

    async def mock_notify(channels, title, content):
        return [{"channel": ch.get("type", ""), "success": True, "error": None} for ch in channels]

    monkeypatch.setattr(notify_client, "notify", mock_notify)
    monkeypatch.setattr(notif_ep, "notify", mock_notify)

    token = await _register_and_login(client, "nbci@test.com")
    h = _auth_headers(token)

    # 先配置一个渠道
    resp = await client.post("/api/v1/push/channels", json={
        "name": "tg",
        "type": "telegram",
        "config": {"bot_token": "secret-token", "chat_id": "123456"},
    }, headers=h)
    ch_id = resp.json()["id"]

    # 按渠道 id 推送
    resp = await client.post("/api/v1/notifications/send", json={
        "title": "测试",
        "content": "hello",
        "channel_ids": [ch_id],
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["results"][0]["success"] is True


# ── 文件工作区 (mock MinIO) ──

@pytest.fixture
def mock_minio(monkeypatch):
    """Mock MinIO 客户端, 使文件工作区测试不依赖对象存储。

    files.py 顶部 `from app.core.minio_client import ...` 绑定后,
    需同时 patch minio_client 模块与 files 端点模块命名空间才生效。
    """
    from app.core import minio_client
    from app.api.v1.endpoints import files as files_ep
    store = {}

    def fake_upload(object_name, data, content_type="application/octet-stream"):
        store[object_name] = (data, content_type)
        return object_name

    def fake_download(object_name):
        return store[object_name][0]

    def fake_presigned(object_name, expires_hours=1):
        return f"http://minio.local/{object_name}?expires={expires_hours}"

    def fake_delete(object_name):
        store.pop(object_name, None)

    for mod in (minio_client, files_ep):
        monkeypatch.setattr(mod, "upload_file", fake_upload)
        monkeypatch.setattr(mod, "download_file", fake_download)
        monkeypatch.setattr(mod, "get_presigned_url", fake_presigned)
        monkeypatch.setattr(mod, "delete_file", fake_delete)
    return store


@pytest.mark.asyncio
async def test_file_workspace_crud(client, mock_minio):
    """测试文件工作区 上传/列表/下载/分享/删除。"""
    token = await _register_and_login(client, "fw@test.com")
    h = _auth_headers(token)

    # 上传
    resp = await client.post(
        "/api/v1/files",
        files={"file": ("note.txt", b"hello world", "text/plain")},
        headers=h,
    )
    assert resp.status_code == 201
    file_id = resp.json()["id"]
    assert resp.json()["filename"] == "note.txt"

    # 列表
    resp = await client.get("/api/v1/files", headers=h)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 下载
    resp = await client.get(f"/api/v1/files/{file_id}", headers=h)
    assert resp.status_code == 200
    assert resp.content == b"hello world"

    # 分享
    resp = await client.get(f"/api/v1/files/{file_id}/share", headers=h)
    assert resp.status_code == 200
    assert "minio.local" in resp.json()["url"]

    # 删除
    resp = await client.delete(f"/api/v1/files/{file_id}", headers=h)
    assert resp.status_code == 204
    resp = await client.get("/api/v1/files", headers=h)
    assert len(resp.json()) == 0


# ── WP6: 文件记忆与本地工具修复 ──

@pytest.mark.asyncio
async def test_file_download_chinese_filename(client, mock_minio):
    """中文文件名下载: Content-Disposition 使用 RFC5987 编码。"""
    from urllib.parse import quote

    token = await _register_and_login(client, "zhfile@test.com")
    h = _auth_headers(token)
    resp = await client.post(
        "/api/v1/files",
        files={"file": ("报告 2026.txt", b"data", "text/plain")},
        headers=h,
    )
    assert resp.status_code == 201
    file_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/files/{file_id}", headers=h)
    assert resp.status_code == 200
    cd = resp.headers["content-disposition"]
    assert "filename*=UTF-8''" in cd
    assert quote("报告 2026.txt", safe="") in cd


@pytest.mark.asyncio
async def test_file_upload_minio_failure_503(client, monkeypatch):
    """MinIO S3Error → 503, 不暴露内部错误。"""
    from minio.error import S3Error

    from app.api.v1.endpoints import files as files_ep

    def boom(*args, **kwargs):
        raise S3Error(None, "NoSuchBucket", "bucket gone", "res", "req", "host")

    monkeypatch.setattr(files_ep, "upload_file", boom)

    token = await _register_and_login(client, "s3fail@test.com")
    resp = await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_file_download_minio_failure_503(client, mock_minio, monkeypatch):
    """下载时 MinIO S3Error → 503。"""
    from minio.error import S3Error

    from app.api.v1.endpoints import files as files_ep

    token = await _register_and_login(client, "s3dl@test.com")
    h = _auth_headers(token)
    resp = await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=h,
    )
    file_id = resp.json()["id"]

    def boom(*args, **kwargs):
        raise S3Error(None, "InternalError", "minio down", "res", "req", "host")

    monkeypatch.setattr(files_ep, "download_file", boom)
    resp = await client.get(f"/api/v1/files/{file_id}", headers=h)
    assert resp.status_code == 503


def test_minio_presigned_public_host(monkeypatch):
    """预签名 URL 按 minio_public_url 替换公网 host (契约1)。"""
    from app.core import minio_client
    from app.core.config import settings

    raw = "http://localhost:9000/bucket/obj.txt?X-Amz-Signature=abc"
    # 未配置 → 原样返回
    assert minio_client._apply_public_host(raw) == raw
    # 带 scheme 的公网地址
    monkeypatch.setattr(settings, "minio_public_url", "https://files.example.com", raising=False)
    url = minio_client._apply_public_host(raw)
    assert url == "https://files.example.com/bucket/obj.txt?X-Amz-Signature=abc"
    # 纯 host:port 写法保留原 scheme
    monkeypatch.setattr(settings, "minio_public_url", "files.example.com:9443", raising=False)
    url = minio_client._apply_public_host(raw)
    assert url == "http://files.example.com:9443/bucket/obj.txt?X-Amz-Signature=abc"


@pytest.mark.asyncio
async def test_local_agent_tool_call_http_error_not_fake_success(client, monkeypatch):
    """OpenClaw 返回 5xx → success=False + error, 不伪装成功。"""
    from app.services import local_agent_service

    class _Resp:
        status_code = 500
        text = "internal error"

        def json(self):
            return {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _Resp()

        async def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr(local_agent_service.httpx, "AsyncClient", _FakeClient)

    token = await _register_and_login(client, "toolfail@test.com")
    resp = await client.post(
        "/api/v1/local-agent/tools/web_search/call",
        json={"parameters": {"query": "hello"}},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert data["error"]


@pytest.mark.asyncio
async def test_local_agent_tool_call_unknown_tool(client):
    """调用前校验 tool_id: 不存在的工具 → success=False。"""
    token = await _register_and_login(client, "tool404@test.com")
    resp = await client.post(
        "/api/v1/local-agent/tools/nonexistent_tool_xyz/call",
        json={"parameters": {}},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "不存在" in data["error"]


@pytest.mark.asyncio
async def test_memory_upsert_same_key(client):
    """同 user+key+session 重复创建 → 更新而非新增 (upsert)。"""
    token = await _register_and_login(client, "memup@test.com")
    h = _auth_headers(token)

    r1 = await client.post("/api/v1/memories", json={
        "type": "context", "key": "fav", "value": {"v": 1},
    }, headers=h)
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/memories", json={
        "type": "preference", "key": "fav", "value": {"v": 2},
    }, headers=h)
    assert r2.status_code == 201
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.json()["value"] == {"v": 2}
    assert r2.json()["type"] == "preference"

    resp = await client.get("/api/v1/memories", headers=h)
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_memory_upsert_integrity_fallback(db_engine, monkeypatch):
    """模拟并发竞态: 预查不可见 → 插入撞唯一约束 → IntegrityError 转 update。"""
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.models.memory import MemoryType
    from app.services import memory_service

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    uid = _uuid.uuid4()

    async with factory() as s1:
        m1 = await memory_service.save_memory(s1, uid, MemoryType.context, "race", {"v": 1}, session_id="s-1")

    real_get = memory_service.get_memory
    calls = {"n": 0}

    async def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # 模拟竞态: 预查时对方事务尚未可见
        return await real_get(*args, **kwargs)

    monkeypatch.setattr(memory_service, "get_memory", fake_get)

    async with factory() as s2:
        m2 = await memory_service.save_memory(s2, uid, MemoryType.context, "race", {"v": 2}, session_id="s-1")
    assert m2.id == m1.id
    assert m2.value == {"v": 2}


@pytest.mark.asyncio
async def test_memory_search_escapes_wildcards(client):
    """搜索关键词中的 % _ 被转义, 不作为通配符匹配。"""
    token = await _register_and_login(client, "memesc@test.com")
    h = _auth_headers(token)

    await client.post("/api/v1/memories", json={
        "type": "context", "key": "100% complete", "value": {"note": "a"},
    }, headers=h)
    await client.post("/api/v1/memories", json={
        "type": "context", "key": "1000 items", "value": {"note": "b"},
    }, headers=h)

    resp = await client.get("/api/v1/memories/search", params={"q": "100%"}, headers=h)
    assert resp.status_code == 200
    keys = [m["key"] for m in resp.json()]
    assert keys == ["100% complete"]
