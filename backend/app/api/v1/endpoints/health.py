"""健康检查端点。对齐 PRD 8.3 可观测性要求。"""

import asyncio

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_session_factory

router = APIRouter(prefix="/health", tags=["健康检查"])


async def _embedding_health_status() -> str:
    """Return the active embedding backend status without requiring optional TEI."""
    from app.core import embedding_config

    if embedding_config.is_configured():
        from app.core.tei_client import _embed_via_api

        cfg = embedding_config.get()
        try:
            vectors = await _embed_via_api(
                ["Klaw embedding health check"],
                cfg["base_url"],
                cfg["api_key"],
                cfg["model"],
                5.0,
            )
        except Exception as exc:
            return f"error: embedding API {exc.__class__.__name__}"

        dimensions = len(vectors[0]) if vectors else 0
        if dimensions != settings.embedding_dim:
            return f"error: embedding API returned {dimensions} dimensions"
        return "ok: embedding API"

    from app.core.tei_client import health_check as tei_health

    return "ok" if await tei_health() else "error: unhealthy"


def _status_is_healthy(value: str) -> bool:
    return value == "ok" or value.startswith("ok:")


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
            checks["elasticsearch"] = "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
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
        await asyncio.to_thread(client.list_buckets)
        checks["minio"] = "ok"
    except Exception as e:
        checks["minio"] = f"error: {e.__class__.__name__}"

    # OpenClaw
    try:
        from app.core.llm_client import health_check as openclaw_health

        checks["openclaw"] = "ok" if await openclaw_health() else "error: chat API unavailable"
    except Exception as e:
        checks["openclaw"] = f"error: {e.__class__.__name__}"

    # Hermes — 消息网关 (Telegram/Discord/Slack bridge)
    # API server 默认关闭时，后端无法验证或调用 Hermes，不能报告为可用。
    try:
        import httpx

        # 尝试连接 Hermes gateway 的 HTTP 端口 (如配置了 API server)
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{settings.hermes_url}/health")
            checks["hermes"] = "ok" if resp.status_code == 200 else f"error: HTTP {resp.status_code}"
    except Exception as e:
        checks["hermes"] = f"error: unavailable ({e.__class__.__name__})"

    # Embedding API is primary. TEI is an optional local fallback.
    try:
        checks["embedding"] = await _embedding_health_status()
    except Exception as e:
        checks["embedding"] = f"error: {e.__class__.__name__}"

    # Reranker (Cross-Encoder — BGE reranker)
    try:
        from app.core.reranker_client import health_check as reranker_health
        if await reranker_health():
            checks["reranker"] = "ok"
        else:
            checks["reranker"] = "error: unhealthy"
    except Exception as e:
        checks["reranker"] = f"error: {e.__class__.__name__}"

    all_ok = all(_status_is_healthy(v) for v in checks.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "checks": checks,
    }
