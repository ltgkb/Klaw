"""对话式 Agent Pydantic 模型。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.conversation import MessageRole


class MessageRead(BaseModel):
    """消息响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    created_at: datetime


class ChatRequest(BaseModel):
    """发起一轮对话。"""

    message: str


class ChatResponse(BaseModel):
    """对话触发响应 (异步, 需轮询 messages 获取回答)。"""

    execution_id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
