"""健康检查端点测试: 单点故障 → 整体 degraded。"""

import pytest


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
