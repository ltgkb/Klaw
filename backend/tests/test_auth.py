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


# ── WP1 Auth 安全基线：禁用用户 / 畸形 sub / 最后 admin / 并发注册竞态 ──


@pytest.mark.asyncio
async def test_disabled_user_token_rejected(client, db_session):
    """被禁用用户的 access token 应返回 401 (P1-1)。"""
    from sqlalchemy import select

    from app.models.user import User

    await client.post("/api/v1/auth/register", json={
        "email": "disabled@test.com", "name": "Disabled", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "disabled@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]

    # 禁用前 token 可用
    ok_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok_resp.status_code == 200

    # 直接改库禁用该用户
    result = await db_session.execute(select(User).where(User.email == "disabled@test.com"))
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_sub_access_token_rejected(client):
    """sub 非合法 UUID 的 access token 应返回 401 而非 500 (P1-4)。"""
    from app.core.security import create_access_token

    token = create_access_token(subject="not-a-uuid")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_sub_refresh_token_rejected(client):
    """sub 非合法 UUID 的 refresh token 应返回 401 而非 500 (P1-4)。"""
    from app.core.security import create_refresh_token

    refresh = create_refresh_token(subject="not-a-uuid")
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_last_admin_cannot_be_demoted(client):
    """最后一个 admin 不可被降级 (P2-9)。"""
    await client.post("/api/v1/auth/register", json={
        "email": "sole-admin@test.com", "name": "Admin", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "sole-admin@test.com", "password": "secret123",
    })
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    admin_id = me_resp.json()["id"]

    resp = await client.put(
        f"/api/v1/users/{admin_id}/role", params={"role": "user"}, headers=headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_admin_demote_allowed_when_multiple_admins(client):
    """存在多个 admin 时允许降级其中一个 (P2-9)。"""
    await client.post("/api/v1/auth/register", json={
        "email": "admin1@test.com", "name": "Admin1", "password": "secret123",
    })
    await client.post("/api/v1/auth/register", json={
        "email": "admin2@test.com", "name": "Admin2", "password": "secret123",
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "admin1@test.com", "password": "secret123",
    })
    headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    admin1_id = me_resp.json()["id"]

    users_resp = await client.get("/api/v1/users", headers=headers)
    admin2_id = next(u["id"] for u in users_resp.json() if u["email"] == "admin2@test.com")

    # 提升 admin2 为 admin 后，admin1 可被降级
    promote = await client.put(
        f"/api/v1/users/{admin2_id}/role", params={"role": "admin"}, headers=headers
    )
    assert promote.status_code == 200
    demote = await client.put(
        f"/api/v1/users/{admin1_id}/role", params={"role": "user"}, headers=headers
    )
    assert demote.status_code == 200
    assert demote.json()["role"] == "user"


@pytest.mark.asyncio
async def test_register_user_integrity_error_becomes_conflict():
    """并发注册竞态下唯一约束冲突应转为 ValueError (端点映射 409) (P2-6)。"""
    from unittest.mock import AsyncMock, MagicMock

    from sqlalchemy.exc import IntegrityError

    from app.schemas.auth import UserRegister
    from app.services.user_service import register_user

    db = AsyncMock()
    db.add = MagicMock()  # Session.add 是同步方法
    # 预检查：邮箱不存在、已有其他用户（非首个）
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    db.commit.side_effect = IntegrityError("INSERT INTO users", {}, Exception("unique"))

    with pytest.raises(ValueError, match="该邮箱已注册"):
        await register_user(
            db, UserRegister(email="race@test.com", name="Race", password="secret123")
        )
    db.rollback.assert_awaited_once()
