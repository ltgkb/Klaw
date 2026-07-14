"""模型供应商端点占位 (P0 路由骨架)。对齐 PRD 6.3。

M4 实现统一模型抽象层、OpenClaw/Hermes/OpenAI 接入与 fallback 路由。
"""

from fastapi import APIRouter

router = APIRouter(prefix="/providers", tags=["模型供应商"])


@router.get("")
async def list_providers():
    """列出已配置的模型供应商。M4 实现。"""
    return {
        "providers": [
            {"name": "openclaw", "status": "pending", "priority": "P0", "deploy": "local"},
            {"name": "hermes", "status": "pending", "priority": "P0", "deploy": "local"},
            {"name": "openai", "status": "pending", "priority": "P0", "deploy": "cloud"},
            {"name": "anthropic", "status": "pending", "priority": "P1", "deploy": "cloud"},
            {"name": "ollama", "status": "pending", "priority": "P1", "deploy": "local"},
        ]
    }


@router.get("/models")
async def list_models():
    """可用模型列表。M4 实现。"""
    return {"models": [], "note": "M4 实现: 从各供应商拉取可用模型列表"}


@router.post("/chat")
async def chat():
    """统一对话接口。M4 实现。"""
    return {"note": "M4 实现: 统一 chat/completions，OpenClaw 优先 + OpenAI fallback"}


@router.post("/chat/stream")
async def chat_stream():
    """统一流式对话。M4 实现。"""
    return {"note": "M4 实现: SSE 流式 chat"}
