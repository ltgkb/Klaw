"""健康检查端点测试: 单点故障 → 整体 degraded。"""

import logging

import pytest


@pytest.fixture(autouse=True)
def isolate_health_dependencies(db_engine, monkeypatch):
    """Keep endpoint contract tests independent from workstation services."""
    import httpx
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.api.v1.endpoints import health
    from app.core import llm_client, reranker_client, tei_client

    monkeypatch.setattr(
        health,
        "async_session_factory",
        async_sessionmaker(db_engine, expire_on_commit=False),
    )

    class _Redis:
        async def ping(self):
            return True

        async def aclose(self):
            return None

    monkeypatch.setattr(aioredis, "from_url", lambda *args, **kwargs: _Redis())

    class _Response:
        status_code = 200

    class _HttpClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", _HttpClient)

    class _Minio:
        def __init__(self, *args, **kwargs):
            pass

        def list_buckets(self):
            return []

    monkeypatch.setattr("minio.Minio", _Minio)

    async def healthy():
        return True

    monkeypatch.setattr(llm_client, "health_check", healthy)
    monkeypatch.setattr(tei_client, "health_check", healthy)
    monkeypatch.setattr(reranker_client, "health_check", healthy)


def test_http_transport_loggers_do_not_log_sensitive_urls():
    """Webhook/token 位于 URL 路径时，通用 HTTP transport 不得记录 INFO/DEBUG URL。"""
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


@pytest.mark.asyncio
async def test_health_returns_status_and_checks(client):
    """健康检查返回 200, 含 status 与各组件 checks。"""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("healthy", "degraded")
    assert isinstance(data["checks"], dict)
    # 关键组件均在检查列表中
    for component in ("postgres", "redis", "elasticsearch", "minio"):
        assert component in data["checks"]


@pytest.mark.asyncio
async def test_health_single_component_failure_degraded(client, monkeypatch):
    """单个组件 (embedding 后端) 故障 → 整体状态 degraded, 该组件标记 error。

    health 端点以 "embedding" 命名该检查 (embedding API 优先, TEI 为可选兜底);
    未配置 embedding API 时回落 TEI health_check, 其结果体现在 checks["embedding"]。
    """
    from app.core import embedding_config, tei_client

    async def fake_tei_health():
        return False

    monkeypatch.setattr(embedding_config, "is_configured", lambda: False)
    monkeypatch.setattr(tei_client, "health_check", fake_tei_health)

    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["embedding"] == "error: unhealthy"


@pytest.mark.asyncio
async def test_health_component_exception_degraded(client, monkeypatch):
    """组件健康检查抛异常 → 整体 degraded, 异常被捕获记为 error。"""
    from app.core import reranker_client

    async def fake_reranker_health():
        raise ConnectionError("reranker unreachable")

    monkeypatch.setattr(reranker_client, "health_check", fake_reranker_health)

    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["reranker"].startswith("error")
