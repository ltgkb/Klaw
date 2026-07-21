"""系统配置端点测试: admin 权限 / embedding clear_key / llm-config 热更新 / providers 认证。"""

import pytest

from app.core import embedding_config, llm_config
from tests.test_m4 import _auth_headers


async def _register_and_login(client, email, password="secret123"):
    """注册并登录, 返回 access_token。首个注册用户为 admin。"""
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "User", "password": password,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"]


@pytest.fixture(autouse=True)
def _restore_caches():
    """每个测试后还原 embedding_config / llm_config 内存缓存。"""
    emb_before = embedding_config.get()
    llm_before = llm_config.get_cached()
    yield
    with embedding_config._lock:
        embedding_config._cache.update(emb_before)
    with llm_config._lock:
        llm_config._cache.update(llm_before)


# ── admin 权限 (Auth P1-3) ──


@pytest.mark.asyncio
async def test_embedding_config_put_requires_admin(client):
    """非 admin 修改 embedding 配置 → 403; admin → 200。"""
    admin_token = await _register_and_login(client, "ss-admin@test.com")
    user_token = await _register_and_login(client, "ss-user@test.com")

    body = {"base_url": "http://emb.example/v1", "api_key": "sk-emb", "model": "bge-m3"}
    resp = await client.put("/api/v1/system/embedding-config", json=body, headers=_auth_headers(user_token))
    assert resp.status_code == 403

    resp = await client.put("/api/v1/system/embedding-config", json=body, headers=_auth_headers(admin_token))
    assert resp.status_code == 200
    assert resp.json()["has_key"] is True
    assert resp.json()["configured"] is True


@pytest.mark.asyncio
async def test_llm_config_put_requires_admin(client):
    """非 admin 修改 LLM 配置 → 403; admin → 200。"""
    admin_token = await _register_and_login(client, "lc-admin@test.com")
    user_token = await _register_and_login(client, "lc-user@test.com")

    body = {"default_model": "glm-4.5-air"}
    resp = await client.put("/api/v1/system/llm-config", json=body, headers=_auth_headers(user_token))
    assert resp.status_code == 403

    resp = await client.put("/api/v1/system/llm-config", json=body, headers=_auth_headers(admin_token))
    assert resp.status_code == 200
    assert resp.json()["default_model"] == "glm-4.5-air"


@pytest.mark.asyncio
async def test_config_endpoints_require_auth(client):
    """未登录访问配置端点 → 401。"""
    resp = await client.get("/api/v1/system/embedding-config")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/system/llm-config")
    assert resp.status_code == 401
    resp = await client.put("/api/v1/system/embedding-config", json={})
    assert resp.status_code == 401
    resp = await client.put("/api/v1/system/llm-config", json={})
    assert resp.status_code == 401


# ── embedding clear_key (P2-6) ──


@pytest.mark.asyncio
async def test_embedding_config_clear_key(client):
    """clear_key=true 显式清除已保存的 api_key; 默认空 api_key 保留已有 Key。"""
    admin_token = await _register_and_login(client, "ck-admin@test.com")
    h = _auth_headers(admin_token)

    resp = await client.put("/api/v1/system/embedding-config", json={
        "base_url": "http://emb.example/v1", "api_key": "sk-emb", "model": "bge-m3",
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["has_key"] is True

    # 空 api_key 保留已有 Key
    resp = await client.put("/api/v1/system/embedding-config", json={
        "base_url": "http://emb2.example/v1", "model": "bge-m3",
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["has_key"] is True
    assert resp.json()["base_url"] == "http://emb2.example/v1"

    # clear_key 显式清除
    resp = await client.put("/api/v1/system/embedding-config", json={
        "base_url": "http://emb2.example/v1", "model": "bge-m3", "clear_key": True,
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["has_key"] is False
    assert resp.json()["configured"] is False


# ── llm-config Key 热更新 (P1-3) ──


@pytest.mark.asyncio
async def test_llm_config_key_hot_update(client):
    """PUT 写入 Key 后内存缓存即时生效; 空 Key 保留已有值。"""
    admin_token = await _register_and_login(client, "hot-admin@test.com")
    h = _auth_headers(admin_token)

    resp = await client.put("/api/v1/system/llm-config", json={
        "default_model": "glm-4.5-air", "kaiweb_api_key": "sk-hot-kaiweb",
    }, headers=h)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_kaiweb_key"] is True
    assert data["has_openai_key"] is False
    # 热更新: 内存缓存立即可读
    assert llm_config.get_key("kaiweb") == "sk-hot-kaiweb"

    # 空 Key 保留已有值
    resp = await client.put("/api/v1/system/llm-config", json={
        "default_model": "gpt-4o-mini",
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["has_kaiweb_key"] is True
    assert llm_config.get_key("kaiweb") == "sk-hot-kaiweb"

    # GET 读取 (普通登录用户可读, key 脱敏)
    user_token = await _register_and_login(client, "hot-user@test.com")
    resp = await client.get("/api/v1/system/llm-config", headers=_auth_headers(user_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_model"] == "gpt-4o-mini"
    assert data["has_kaiweb_key"] is True
    assert "sk-hot-kaiweb" not in str(data)


# ── providers 端点认证 (Auth 附带) ──


@pytest.mark.asyncio
async def test_providers_endpoints_require_auth(client):
    """GET /providers 与 /providers/models 未登录 → 401; 登录 → 200。"""
    resp = await client.get("/api/v1/providers")
    assert resp.status_code == 401
    resp = await client.get("/api/v1/providers/models")
    assert resp.status_code == 401

    token = await _register_and_login(client, "prov-auth@test.com")
    h = _auth_headers(token)
    resp = await client.get("/api/v1/providers", headers=h)
    assert resp.status_code == 200
    resp = await client.get("/api/v1/providers/models", headers=h)
    assert resp.status_code == 200
