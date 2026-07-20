"""新增接口测试: 本地工具发现 / 文件工作区 / 推送渠道配置。"""

import pytest

from tests.test_m4 import _auth_headers, _register_and_login


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
