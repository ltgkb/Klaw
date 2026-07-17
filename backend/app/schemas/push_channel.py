"""推送渠道配置 Pydantic 模型。对齐 PRD 6.6。

渠道敏感字段 (webhook_url / bot_token) 在 DB 中加密存储, API 返回时脱敏。
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.push_channel import ChannelType


class ChannelConfigIn(BaseModel):
    """创建/更新渠道时的配置 (明文, 服务端加密)。"""

    webhook_url: str | None = None
    bot_token: str | None = None
    chat_id: str | None = None
    channel: str | None = None


class PushChannelCreate(BaseModel):
    """创建推送渠道。"""

    name: str
    type: ChannelType
    config: ChannelConfigIn = ChannelConfigIn()


class PushChannelRead(BaseModel):
    """渠道响应 (脱敏)。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: ChannelType
    config: dict[str, Any]  # 已脱敏
    created_at: datetime
