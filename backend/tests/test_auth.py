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
async def test_disabled_user_token_is_rejected(client, db_engine):
    """禁用用户已有的 access token 也必须立即失效。"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.user import User

    await client.post("/api/v1/auth/register", json={
        "email": "disabled@test.com", "name": "Disabled", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "disabled@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as db:
        result = await db.execute(select(User).where(User.email == "disabled@test.com"))
        user = result.scalar_one()
        user.is_active = False
        await db.commit()

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


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
async def test_admin_can_toggle_user_active_state_but_not_self(client):
    await client.post("/api/v1/auth/register", json={
        "email": "admin-status@test.com", "name": "Admin", "password": "secret123",
    })
    user_resp = await client.post("/api/v1/auth/register", json={
        "email": "target-status@test.com", "name": "Target", "password": "secret123",
    })
    target_id = user_resp.json()["id"]
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "admin-status@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    disabled = await client.put(f"/api/v1/users/{target_id}/status", json={"is_active": False}, headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False

    self_id = (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]
    self_disabled = await client.put(f"/api/v1/users/{self_id}/status", json={"is_active": False}, headers=headers)
    assert self_disabled.status_code == 400
    self_demoted = await client.put(
        f"/api/v1/users/{self_id}/role",
        params={"role": "user"},
        headers=headers,
    )
    assert self_demoted.status_code == 400


@pytest.mark.asyncio
async def test_regular_user_cannot_toggle_user_active_state(client):
    await client.post("/api/v1/auth/register", json={
        "email": "admin-status2@test.com", "name": "Admin", "password": "secret123",
    })
    target = await client.post("/api/v1/auth/register", json={
        "email": "target-status2@test.com", "name": "Target", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "target-status2@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]
    resp = await client.put(
        f"/api/v1/users/{target.json()['id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_role_change_applies_to_existing_access_token(client):
    await client.post("/api/v1/auth/register", json={
        "email": "role-admin@test.com", "name": "Admin", "password": "secret123",
    })
    target_resp = await client.post("/api/v1/auth/register", json={
        "email": "role-target@test.com", "name": "Target", "password": "secret123",
    })
    admin_login = await client.post("/api/v1/auth/login", json={
        "email": "role-admin@test.com", "password": "secret123",
    })
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    target_id = target_resp.json()["id"]

    promoted = await client.put(
        f"/api/v1/users/{target_id}/role",
        params={"role": "admin"},
        headers=admin_headers,
    )
    assert promoted.status_code == 200
    target_login = await client.post("/api/v1/auth/login", json={
        "email": "role-target@test.com", "password": "secret123",
    })
    target_headers = {"Authorization": f"Bearer {target_login.json()['access_token']}"}
    assert (await client.get("/api/v1/users", headers=target_headers)).status_code == 200

    demoted = await client.put(
        f"/api/v1/users/{target_id}/role",
        params={"role": "user"},
        headers=admin_headers,
    )
    assert demoted.status_code == 200
    assert (await client.get("/api/v1/users", headers=target_headers)).status_code == 403


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
