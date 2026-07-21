"""负向用例测试: 越权访问 / 非法输入 / 无效凭据。

覆盖:
- 非 admin 查询其他用户 → 403
- 空文件上传 → 400 / 超大文件上传 → 413
- 坏 refresh token → 401
- 下载他人文件 → 404
"""

import pytest

from tests.test_m4 import _auth_headers, _register_and_login


@pytest.fixture
def mock_minio(monkeypatch):
    """Mock MinIO 客户端, 使文件工作区测试不依赖对象存储。"""
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


async def _register(client, email, password="secret123"):
    """注册并返回 (access_token, user_id)。"""
    resp = await client.post("/api/v1/auth/register", json={
        "email": email, "name": "Neg User", "password": password,
    })
    assert resp.status_code == 201
    user_id = resp.json()["id"]
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"], user_id


# ── 越权: 非 admin 查他人 ──

@pytest.mark.asyncio
async def test_non_admin_get_other_user_forbidden(client):
    """普通用户查询其他用户详情 → 403。"""
    _, admin_id = await _register(client, "neg-admin@test.com")  # 首个用户为 admin
    member_token, _ = await _register(client, "neg-member@test.com")

    resp = await client.get(f"/api/v1/users/{admin_id}", headers=_auth_headers(member_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_list_users_forbidden(client):
    """普通用户请求用户列表 (admin only) → 403。"""
    await _register(client, "neg-admin2@test.com")
    member_token, _ = await _register(client, "neg-member2@test.com")

    resp = await client.get("/api/v1/users", headers=_auth_headers(member_token))
    assert resp.status_code == 403


# ── 非法输入: 空文件 / 超大文件 ──

@pytest.mark.asyncio
async def test_upload_empty_file_rejected(client, mock_minio):
    """上传空文件 → 400。"""
    token = await _register_and_login(client, "neg-empty@test.com")
    resp = await client.post(
        "/api/v1/files",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected(client, mock_minio, monkeypatch):
    """上传超过大小限制的文件 → 413 (限制值 monkeypatch 调小以免构造超大 payload)。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_size", 10)
    token = await _register_and_login(client, "neg-big@test.com")
    resp = await client.post(
        "/api/v1/files",
        files={"file": ("big.bin", b"x" * 11, "application/octet-stream")},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 413


# ── 无效凭据: 坏 refresh token ──

@pytest.mark.asyncio
async def test_refresh_with_garbage_token_unauthorized(client):
    """畸形 refresh token → 401。"""
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token_unauthorized(client):
    """用 access token (type != refresh) 调 refresh → 401。"""
    token = await _register_and_login(client, "neg-refresh@test.com")
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401


# ── 越权: 下载他人文件 ──

@pytest.mark.asyncio
async def test_download_other_users_file_not_found(client, mock_minio):
    """下载他人工作区文件 → 404 (不泄露存在性)。"""
    owner_token, _ = await _register(client, "neg-owner@test.com")
    other_token, _ = await _register(client, "neg-other@test.com")

    resp = await client.post(
        "/api/v1/files",
        files={"file": ("secret.txt", b"owner data", "text/plain")},
        headers=_auth_headers(owner_token),
    )
    assert resp.status_code == 201
    file_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/files/{file_id}", headers=_auth_headers(other_token))
    assert resp.status_code == 404
