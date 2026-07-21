"""推送渠道配置端点。对齐 PRD 6.6。

管理用户持久化的推送渠道 (飞书/企微/Telegram/Hermes), 仅敏感字段加密存储,
chat_id / channel 等非敏感字段明文存储以便回显与分发。
现有 /notifications/send 仍用于一次性即时推送。
"""

import logging
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DBSession
from app.models.push_channel import ChannelType, PushChannel
from app.schemas.push_channel import SENSITIVE_CONFIG_KEYS, PushChannelCreate, PushChannelRead
from app.utils.crypto import encrypt

logger = logging.getLogger("claw.push_channels")

router = APIRouter(prefix="/push", tags=["推送渠道"])

# 敏感字段名 — 返回时脱敏
_SENSITIVE_KEYS = SENSITIVE_CONFIG_KEYS

# 各渠道类型已知的 Webhook 主机白名单 (prod 环境严格执行)
_HOST_WHITELIST = {
    ChannelType.feishu: {"open.feishu.cn", "open.larksuite.com"},
    ChannelType.wechat: {"qyapi.weixin.qq.com"},
}


def _mask_config(config: dict) -> dict:
    """脱敏渠道配置 (隐藏敏感字段值, 仅保留是否已配置)。"""
    masked = {}
    for k, v in (config or {}).items():
        if k in _SENSITIVE_KEYS and v:
            masked[k] = "******"
        else:
            masked[k] = v
    return masked


def _validate_webhook_host(ch_type: ChannelType, webhook_url: str) -> None:
    """创建渠道时按类型校验 Webhook host 白名单。

    - 命中白名单直接放行
    - 未命中: prod 环境拒绝 (400); dev/staging 环境放行但记 warning 便于联调
    """
    host = (urlparse(webhook_url).hostname or "").lower()
    whitelist = _HOST_WHITELIST.get(ch_type, set())
    if not whitelist or host in whitelist:
        return
    if settings.environment == "prod":
        logger.warning("推送渠道 Webhook host 不在白名单, 已拒绝: type=%s host=%s", ch_type.value, host)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{ch_type.value} 渠道的 Webhook 主机不在允许列表: {host or '(无主机)'}",
        )
    logger.warning("推送渠道 Webhook host 不在白名单 (%s 环境放行): type=%s host=%s",
                   settings.environment, ch_type.value, host)


@router.get("/channels", response_model=list[PushChannelRead])
async def list_channels(current_user: CurrentUser, db: DBSession):
    """列出当前用户已配置的推送渠道。"""
    result = await db.execute(
        select(PushChannel)
        .where(PushChannel.owner_id == current_user.id)
        .order_by(PushChannel.created_at.desc())
    )
    channels = result.scalars().all()
    return [
        PushChannelRead.model_validate(c).model_copy(update={"config": _mask_config(c.config)})
        for c in channels
    ]


@router.post("/channels", response_model=PushChannelRead, status_code=status.HTTP_201_CREATED)
async def create_channel(data: PushChannelCreate, current_user: CurrentUser, db: DBSession):
    """配置新推送渠道 (仅敏感字段加密存储, chat_id/channel 明文以便回显)。"""
    raw = data.config.model_dump(exclude_none=True)
    if data.type in (ChannelType.feishu, ChannelType.wechat):
        _validate_webhook_host(data.type, str(raw.get("webhook_url", "")))
    stored = {
        k: (encrypt(str(v)) if k in _SENSITIVE_KEYS else v)
        for k, v in raw.items()
    }

    channel = PushChannel(
        owner_id=current_user.id,
        name=data.name,
        type=data.type,
        config=stored,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return PushChannelRead.model_validate(channel).model_copy(
        update={"config": _mask_config(channel.config)}
    )


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(channel_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """删除推送渠道。"""
    result = await db.execute(
        select(PushChannel).where(
            PushChannel.id == channel_id, PushChannel.owner_id == current_user.id
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="渠道不存在")
    await db.delete(channel)
    await db.commit()
