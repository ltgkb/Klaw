"""FastAPI 应用入口。对齐 PRD 4.1 API 网关层。"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings

# 结构化日志 (JSON 格式, 按 task_id 关联 — PRD 8.3)
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger("claw")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期: 启动时初始化基础设施资源。"""
    logger.info("应用启动中 — 初始化基础设施资源")

    # MinIO bucket
    try:
        from app.core.minio_client import ensure_bucket
        ensure_bucket()
    except Exception as e:
        logger.warning("MinIO bucket 初始化失败 (将在请求时重试): %s", e)

    # ES 知识库索引
    try:
        from app.core.es_client import ensure_kb_index, get_es_client
        await ensure_kb_index()
    except Exception as e:
        logger.warning("ES 索引初始化失败 (将在请求时重试): %s", e)

    logger.info("基础设施资源初始化完成")

    # APScheduler 定时调度器
    try:
        from app.core.scheduler import init_scheduler
        init_scheduler()
    except Exception as e:
        logger.warning("APScheduler 初始化失败: %s", e)

    # 载入 embedding 模型 API 配置 (system_settings)
    try:
        from app.core.database import async_session_factory
        from app.core import embedding_config
        async with async_session_factory() as db:
            await embedding_config.load_from_db(db)
        logger.info("Embedding 配置已载入: source=%s", embedding_config.get().get("base_url") and "api" or "env/tei")
    except Exception as e:
        logger.warning("Embedding 配置载入失败: %s", e)

    # 载入 LLM 供应商 Key (system_settings, 热更新缓存)
    try:
        from app.core.database import async_session_factory
        from app.core import llm_config
        async with async_session_factory() as db:
            await llm_config.load_from_db(db)
        logger.info("LLM 供应商 Key 已载入")
    except Exception as e:
        logger.warning("LLM 供应商 Key 载入失败: %s", e)

    yield

    # 关闭连接
    logger.info("应用关闭中 — 释放资源")

    # 关闭调度器
    try:
        from app.core.scheduler import shutdown_scheduler
        shutdown_scheduler()
    except Exception as e:
        logger.warning("APScheduler 关闭失败: %s", e)

    try:
        from app.core.es_client import close_es_client
        await close_es_client()
    except Exception as e:
        logger.warning("ES 连接关闭失败: %s", e)
    logger.info("资源释放完成")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Claw-Native Agent 平台 — 本地 OpenClaw/Hermes 为一等公民的 Agent 平台",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 全局异常处理
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "服务器内部错误", "detail": str(exc) if settings.debug else None},
        )

    # 路由
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/")
    async def root():
        return {"app": settings.app_name, "version": "0.1.0", "docs": "/docs"}

    logger.info("应用初始化完成 environment=%s", settings.environment)
    return app


app = create_app()
