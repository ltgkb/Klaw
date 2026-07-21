"""健康检查端点。对齐 PRD 8.3 可观测性要求。"""

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_factory

router = APIRouter(prefix="/health", tags=["健康检查"])


@router.get("")
async def health_check():
    """检查各基础设施连通性: PostgreSQL / Redis / ES / MinIO / OpenClaw / Hermes。"""
    checks: dict[str, str] = {}

    # PostgreSQL
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e.__class__.__name__}"

    # Redis
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e.__class__.__name__}"

    # Elasticsearch
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(settings.es_url)
            checks["elasticsearch"] = "ok" if 200 <= resp.status_code < 300 else f"error: HTTP {resp.status_code}"
    except Exception as e:
        checks["elasticsearch"] = f"error: {e.__class__.__name__}"

    # MinIO
    try:
        from minio import Minio

        client = Minio(
            settings.minio_url,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
        client.list_buckets()
        checks["minio"] = "ok"
    except Exception as e:
        checks["minio"] = f"error: {e.__class__.__name__}"

    # OpenClaw
    try:
        import httpx

        headers = {}
        if settings.openclaw_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_token}"
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.openclaw_url}/health", headers=headers)
            checks["openclaw"] = "ok" if 200 <= resp.status_code < 300 else f"error: HTTP {resp.status_code}"
    except Exception as e:
        checks["openclaw"] = f"error: {e.__class__.__name__}"

    # Hermes — 这里只能确认 HTTP API 连通性。gateway 模式没有 HTTP API
    # 时必须报告不可探测，不能把连接失败当作 running。
    try:
        import httpx

        # 尝试连接 Hermes gateway 的 HTTP 端口 (如配置了 API server)
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{settings.hermes_url}/")
            checks["hermes"] = "ok" if 200 <= resp.status_code < 300 else f"error: HTTP {resp.status_code}"
    except Exception as e:
        checks["hermes"] = f"error: {e.__class__.__name__}"

    # TEI (Text Embeddings Inference — BGE-M3)
    try:
        from app.core.tei_client import health_check as tei_health

        if await tei_health():
            checks["tei"] = "ok"
        else:
            checks["tei"] = "error: unhealthy"
    except Exception as e:
        checks["tei"] = f"error: {e.__class__.__name__}"

    # Reranker (Cross-Encoder — BGE-reranker-v2-m3)
    try:
        from app.core.reranker_client import health_check as reranker_health
        if await reranker_health():
            checks["reranker"] = "ok"
        else:
            checks["reranker"] = "error: unhealthy"
    except Exception as e:
        checks["reranker"] = f"error: {e.__class__.__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }
