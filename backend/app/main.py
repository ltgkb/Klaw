"""FastAPI 应用入口。对齐 PRD 4.1 API 网关层。"""

import logging
import sys

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


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Claw-Native Agent 平台 — 本地 OpenClaw/Hermes 为一等公民的 Agent 平台",
        docs_url="/docs",
        redoc_url="/redoc",
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
