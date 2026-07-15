"""模型供应商 Pydantic 模型。对齐 PRD 6.3 / 第 7 节。"""

from pydantic import BaseModel, Field


class ProviderInfo(BaseModel):
    """供应商状态信息。"""
    name: str
    status: str  # ok / unavailable / not_configured
    deploy: str  # local / cloud
    priority: str  # P0 / P1
    detail: str | None = None


class ModelInfo(BaseModel):
    """可用模型信息。"""
    id: str
    provider: str
    name: str


class ChatMessage(BaseModel):
    """单条对话消息。"""
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    """统一对话请求。"""
    messages: list[ChatMessage]
    model: str = "default"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1, le=32768)


class ChatResponse(BaseModel):
    """统一对话响应。"""
    content: str
    model: str
    provider: str  # openclaw / openai / anthropic


class ChatStreamChunk(BaseModel):
    """流式对话单个 chunk。"""
    content: str
    done: bool = False
