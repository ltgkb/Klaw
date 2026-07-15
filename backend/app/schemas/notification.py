"""推送通知 Pydantic 模型。对齐 PRD M4。"""

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
    """推送请求。"""
    title: str
    content: str
    channels: list[NotifyChannelConfig]


class NotifyResult(BaseModel):
    """单渠道推送结果。"""
    channel: str
    success: bool
    error: str | None = None


class NotifyResponse(BaseModel):
    """推送响应。"""
    results: list[NotifyResult]
