"""认证全链路测试：注册 → 登录 → /me → 刷新 token → RBAC。"""

import pytest


@pytest.mark.asyncio
async def test_register_first_user_is_admin(client):
    """首个注册用户应为 admin。"""
    resp = await client.post("/api/v1/auth/register", json={
        "email": "admin@test.com",
        "name": "Admin",
        "password": "secret123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "admin@test.com"
    assert data["role"] == "admin"
    assert data["has_openai_key"] is False


@pytest.mark.asyncio
async def test_register_second_user_is_regular(client):
    """第二个注册用户应为 user。"""
    await client.post("/api/v1/auth/register", json={
        "email": "admin@test.com", "name": "Admin", "password": "secret123",
    })
    resp = await client.post("/api/v1/auth/register", json={
        "email": "user@test.com", "name": "User", "password": "secret456",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


@pytest.mark.asyncio
async def test_register_duplicate_email_conflict(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "dup@test.com", "name": "A", "password": "secret123",
    })
    assert resp.status_code == 201
    resp2 = await client.post("/api/v1/auth/register", json={
        "email": "dup@test.com", "name": "B", "password": "secret456",
    })
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client):
    await client.post("/api/v1/auth/register", json={
        "email": "login@test.com", "name": "Login", "password": "secret123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "login@test.com", "password": "secret123",
    })
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={
        "email": "wp@test.com", "name": "WP", "password": "secret123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "wp@test.com", "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_valid_token(client):
    await client.post("/api/v1/auth/register", json={
        "email": "me@test.com", "name": "Me", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "me@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@test.com"


@pytest.mark.asyncio
async def test_me_without_token_unauthorized(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client):
    await client.post("/api/v1/auth/register", json={
        "email": "refresh@test.com", "name": "Refresh", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "refresh@test.com", "password": "secret123",
    })
    refresh = login_resp.json()["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_rbac_admin_can_list_users(client):
    await client.post("/api/v1/auth/register", json={
        "email": "admin@test.com", "name": "Admin", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "admin@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_rbac_regular_user_cannot_list_users(client):
    await client.post("/api/v1/auth/register", json={
        "email": "admin@test.com", "name": "Admin", "password": "secret123",
    })
    await client.post("/api/v1/auth/register", json={
        "email": "regular@test.com", "name": "Regular", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "regular@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]

    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_me_encrypts_api_key(client):
    await client.post("/api/v1/auth/register", json={
        "email": "update@test.com", "name": "Update", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "update@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]

    resp = await client.put("/api/v1/users/me", json={"openai_api_key": "sk-test-key-12345"}, headers={
        "Authorization": f"Bearer {token}",
    })
    assert resp.status_code == 200
    assert resp.json()["has_openai_key"] is True

    # 再次获取 /me 确认 has_openai_key 为 true
    me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.json()["has_openai_key"] is True
