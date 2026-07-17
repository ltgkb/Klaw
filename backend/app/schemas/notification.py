"""推送通知 Pydantic 模型。对齐 PRD M4。"""

import uuid
from typing import Any

from pydantic import BaseModel


class NotifyChannelConfig(BaseModel):
    """推送渠道配置。"""
    type: str  # feishu / wechat / telegram / hermes
    # 飞书/企微: webhook_url
    webhook_url: str | None = None
    # Telegram: bot_token + chat_id
    bot_token: str | None = None
    chat_id: str | None = None
    # Hermes: channel
    channel: str | None = None


class NotifyRequest(BaseModel):
    """推送请求。

    channels: 内联渠道配置 (一次性推送)
    channel_ids: 已持久化渠道的 id 列表 (由 /push/channels 配置, 自动解密解析)
    二者至少提供一个。
    """
    title: str
    content: str
    channels: list[NotifyChannelConfig] = []
    channel_ids: list[uuid.UUID] = []


class NotifyResult(BaseModel):
    """单渠道推送结果。"""
    channel: str
    success: bool
    error: str | None = None


class NotifyResponse(BaseModel):
    """推送响应。"""
    results: list[NotifyResult]
