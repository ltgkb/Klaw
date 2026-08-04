"""Security middleware and production configuration tests."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.rate_limit import RateLimitMiddleware


async def test_rate_limit_returns_429(monkeypatch):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.post("/api/v1/auth/login")
    async def login():
        return {"ok": True}

    hits = 0

    async def fake_hit(self, key, limit):
        nonlocal hits
        hits += 1
        return hits, 23

    monkeypatch.setattr(settings, "environment", "staging")
    monkeypatch.setattr(settings, "auth_login_rate_per_minute", 2)
    monkeypatch.setattr(RateLimitMiddleware, "_hit", fake_hit)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.post("/api/v1/auth/login")).status_code == 200
        assert (await client.post("/api/v1/auth/login")).status_code == 200
        response = await client.post("/api/v1/auth/login")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "23"
    assert response.headers["X-RateLimit-Remaining"] == "0"


async def test_external_api_is_identified_by_hashed_key(monkeypatch):
    request = type(
        "RequestStub",
        (),
        {
            "headers": {"x-api-key": "secret-value"},
            "client": None,
        },
    )()
    spec = type("Spec", (), {"identify_by_api_key": True})()
    identifier = RateLimitMiddleware._identifier(request, spec)
    assert identifier.startswith("key:")
    assert "secret-value" not in identifier


def test_client_ip_skips_private_proxy_hops():
    request = type(
        "RequestStub",
        (),
        {
            "headers": {
                "x-forwarded-for": "198.51.100.9, 8.8.8.8, 10.0.1.4",
                "x-real-ip": "10.0.1.4",
            },
            "client": type("Client", (), {"host": "127.0.0.1"})(),
        },
    )()
    assert RateLimitMiddleware._client_ip(request) == "8.8.8.8"


def test_prod_rejects_wildcard_cors():
    try:
        Settings(
            environment="prod",
            jwt_secret_key="x" * 64,
            encryption_key="a" * 64,
            cors_origins=["*"],
            _env_file=None,
        )
    except ValidationError as exc:
        assert "禁止 CORS_ORIGINS 使用通配符" in str(exc)
    else:
        raise AssertionError("prod wildcard CORS must be rejected")


async def test_security_headers_are_present(client):
    response = await client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Request-ID"]


async def test_prod_always_adds_hsts(client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "prod")
    response = await client.get("/")
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")


async def test_external_api_preflight_remains_public(client):
    for endpoint in (
        "/api/v1/kai-knowledge/chat",
        "/api/v1/kai-knowledge/chat/stream",
        "/api/v1/supplier-chat",
    ):
        response = await client.options(
            endpoint,
            headers={
                "Origin": "https://customer.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-API-Key,Content-Type",
            },
        )
        assert response.status_code == 204
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Credentials" not in response.headers
