"""模型供应商端点。对齐 PRD 6.3 / 第 7 节。

统一模型抽象层: OpenClaw/Hermes/OpenAI/Anthropic 接入与 fallback 路由。
"""

import json

import httpx
from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.core.deps import CurrentUser
from app.core import llm_client
from app.core.config import settings
from app.schemas.provider import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderInfo,
)

router = APIRouter(prefix="/providers", tags=["模型供应商"])


@router.get("", response_model=list[ProviderInfo])
async def list_providers():
    """列出已配置的模型供应商及其运行时状态。"""
    providers: list[ProviderInfo] = []

    # OpenClaw (本地优先)
    openclaw_ok = await llm_client.health_check()
    providers.append(ProviderInfo(
        name="openclaw",
        status="ok" if openclaw_ok else "unavailable",
        deploy="local",
        priority="P0",
        detail=settings.openclaw_url,
    ))

    # Hermes (本地备选)
    hermes_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.hermes_url}/")
            hermes_ok = resp.status_code < 500
    except Exception:
        hermes_ok = False
    providers.append(ProviderInfo(
        name="hermes",
        status="ok" if hermes_ok else "unavailable",
        deploy="local",
        priority="P0",
        detail="gateway mode (CLI 调用)",
    ))

    # OpenAI (云端 fallback)
    providers.append(ProviderInfo(
        name="openai",
        status="ok" if settings.openai_api_key else "not_configured",
        deploy="cloud",
        priority="P0",
        detail="需要 API Key",
    ))

    # Anthropic (云端 fallback)
    providers.append(ProviderInfo(
        name="anthropic",
        status="ok" if settings.anthropic_api_key else "not_configured",
        deploy="cloud",
        priority="P1",
        detail="需要 API Key",
    ))

    return providers


@router.get("/models", response_model=list[ModelInfo])
async def list_models():
    """可用模型列表。从 OpenClaw 拉取 + 预定义云端模型。"""
    return await llm_client.list_models()


@router.post("/chat", response_model=ChatResponse)
async def chat(data: ChatRequest, current_user: CurrentUser):
    """统一对话接口。OpenClaw 优先 + OpenAI/Anthropic fallback。"""
    messages = [{"role": m.role, "content": m.content} for m in data.messages]
    try:
        content = await llm_client.chat(
            messages,
            model=data.model,
            user=current_user,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    return ChatResponse(content=content, model=data.model, provider="auto")


@router.post("/chat/stream")
async def chat_stream(data: ChatRequest, current_user: CurrentUser):
    """统一流式对话 (SSE)。"""
    messages = [{"role": m.role, "content": m.content} for m in data.messages]

    async def event_generator():
        try:
            async for chunk in llm_client.chat_stream(
                messages,
                model=data.model,
                user=current_user,
                temperature=data.temperature,
                max_tokens=data.max_tokens,
            ):
                yield {"event": "delta", "data": json.dumps({"content": chunk}, ensure_ascii=False)}
            yield {"event": "done", "data": json.dumps({"done": True})}
        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
