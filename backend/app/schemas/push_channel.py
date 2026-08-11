"""推送渠道配置 Pydantic 模型。对齐 PRD 6.6。

渠道敏感字段 (webhook_url / bot_token) 在 DB 中加密存储, API 返回时脱敏;
chat_id / channel 等非敏感字段明文存储以便回显与分发。
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.push_channel import ChannelType

# 敏感字段名 — DB 中加密存储, API 返回时脱敏 (端点与通知分发共用此常量)
SENSITIVE_CONFIG_KEYS = {"webhook_url", "bot_token"}

# 各渠道类型的必填配置字段
REQUIRED_FIELDS_BY_TYPE = {
    ChannelType.feishu: ("webhook_url",),
    ChannelType.wechat: ("webhook_url",),
    ChannelType.telegram: ("bot_token", "chat_id"),
    ChannelType.hermes: ("channel",),
}


class ChannelConfigIn(BaseModel):
    """创建/更新渠道时的配置 (明文, 服务端加密敏感字段)。"""

    webhook_url: str | None = None
    bot_token: str | None = None
    chat_id: str | None = None
    channel: str | None = None


class PushChannelCreate(BaseModel):
    """创建推送渠道。"""

    name: str = Field(..., min_length=1, max_length=200)
    type: ChannelType
    config: ChannelConfigIn = Field(default_factory=ChannelConfigIn)

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "PushChannelCreate":
        """按渠道类型校验必填字段, 缺失返回 422。"""
        required = REQUIRED_FIELDS_BY_TYPE.get(self.type, ())
        missing = [f for f in required if not getattr(self.config, f, None)]
        if missing:
            raise ValueError(
                f"{self.type.value} 渠道缺少必填配置字段: {', '.join(missing)}"
            )
        return self


class PushChannelUpdate(BaseModel):
    """Update a channel in place so workflow channel_ids remain stable."""

    name: str | None = Field(None, min_length=1, max_length=200)
    type: ChannelType | None = None
    config: ChannelConfigIn | None = None


class PushChannelRead(BaseModel):
    """渠道响应 (脱敏)。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: ChannelType
    config: dict[str, Any]  # 已脱敏
    created_at: datetime
