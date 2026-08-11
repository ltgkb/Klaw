"""模型供应商端点。对齐 PRD 6.3 / 第 7 节。

统一模型抽象层: OpenClaw/Hermes/OpenAI/Anthropic 接入与 fallback 路由。
"""

import json

import httpx
from fastapi import APIRouter, HTTPException, status
from sse_starlette.sse import EventSourceResponse

from app.core.deps import CurrentUser
from app.core import llm_client, llm_config
from app.core.config import settings
from app.schemas.provider import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderInfo,
)

router = APIRouter(prefix="/providers", tags=["模型供应商"])


@router.get("", response_model=list[ProviderInfo])
async def list_providers(_: CurrentUser):
    """列出已配置的模型供应商及其运行时状态。"""
    providers: list[ProviderInfo] = []

    # Kaiweb (自建 OpenAI 兼容网关, 真实 LLM 优先)
    kaiweb_ok = await llm_client.kaiweb_health_check()
    providers.append(ProviderInfo(
        name="kaiweb",
        status="ok" if kaiweb_ok else ("not_configured" if not llm_config.get_key("kaiweb") else "unavailable"),
        deploy="cloud",
        priority="P0",
        detail=settings.kaiweb_base_url,
    ))

    # OpenClaw (本地优先)
    openclaw_ok = await llm_client.health_check()
    openclaw_status = "ok" if openclaw_ok and settings.openclaw_chat_enabled else (
        "not_configured" if openclaw_ok else "unavailable"
    )
    providers.append(ProviderInfo(
        name="openclaw",
        status=openclaw_status,
        deploy="local",
        priority="P0",
        detail=(
            settings.openclaw_url
            if settings.openclaw_chat_enabled
            else f"{settings.openclaw_url} (gateway/tools only; chat disabled)"
        ),
    ))

    # Hermes (本地备选)
    hermes_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{settings.hermes_url}/health")
            hermes_ok = resp.status_code == 200
    except Exception:
        hermes_ok = False
    providers.append(ProviderInfo(
        name="hermes",
        status="ok" if hermes_ok and settings.hermes_chat_enabled else (
            "not_configured" if hermes_ok else "unavailable"
        ),
        deploy="local",
        priority="P0",
        detail=(
            "OpenAI-compatible API server"
            if settings.hermes_chat_enabled
            else "gateway online; inference routing disabled"
        ),
    ))

    # OpenAI (云端 fallback)
    providers.append(ProviderInfo(
        name="openai",
        status="ok" if llm_config.get_key("openai") else "not_configured",
        deploy="cloud",
        priority="P0",
        detail="需要 API Key",
    ))

    # Anthropic (云端 fallback)
    providers.append(ProviderInfo(
        name="anthropic",
        status="ok" if llm_config.get_key("anthropic") else "not_configured",
        deploy="cloud",
        priority="P1",
        detail="需要 API Key",
    ))

    # Mock (dev 兜底, 离线演示)
    if settings.environment == "dev":
        providers.append(ProviderInfo(
            name="mock",
            status="ok",
            deploy="local",
            priority="P2",
            detail="开发兜底 (真实供应商不可用时启用)",
        ))

    return providers


@router.get("/models", response_model=list[ModelInfo])
async def list_models(_: CurrentUser):
    """可用模型列表。从 OpenClaw 拉取 + 预定义云端模型。"""
    return await llm_client.list_models()


@router.post("/chat", response_model=ChatResponse)
async def chat(data: ChatRequest, current_user: CurrentUser):
    """统一对话接口。OpenClaw/Hermes 本地优先，再回退云端供应商。"""
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
