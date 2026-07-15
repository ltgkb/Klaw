"""记忆系统 Pydantic 模型。对齐 PRD 5.1。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.memory import MemoryType


class MemoryCreate(BaseModel):
    """创建记忆。"""
    type: MemoryType = MemoryType.context
    key: str = Field(..., min_length=1, max_length=255)
    value: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None


class MemoryUpdate(BaseModel):
    """更新记忆。"""
    value: dict[str, Any] | None = None


class MemoryRead(BaseModel):
    """记忆响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: MemoryType
    key: str
    value: dict[str, Any]
    session_id: str | None
    created_at: datetime
    updated_at: datetime


class MemorySearchRequest(BaseModel):
    """记忆搜索请求。"""
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    session_id: str | None = None
