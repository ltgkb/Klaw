"""推送渠道配置端点。对齐 PRD 6.6。

管理用户持久化的推送渠道 (飞书/企微/Telegram/Hermes), 敏感字段加密存储。
现有 /notifications/send 仍用于一次性即时推送。
"""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.models.push_channel import PushChannel
from app.schemas.push_channel import PushChannelCreate, PushChannelRead
from app.utils.crypto import decrypt, encrypt

router = APIRouter(prefix="/push", tags=["推送渠道"])

# 敏感字段名 — 返回时脱敏
_SENSITIVE_KEYS = {"webhook_url", "bot_token"}


def _mask_config(config: dict) -> dict:
    """脱敏渠道配置 (隐藏敏感字段值, 仅保留是否已配置)。"""
    masked = {}
    for k, v in (config or {}).items():
        if k in _SENSITIVE_KEYS and v:
            masked[k] = "******"
        else:
            masked[k] = v
    return masked


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
    """配置新推送渠道 (敏感字段加密存储)。"""
    raw = data.config.model_dump(exclude_none=True)
    encrypted = {k: encrypt(str(v)) for k, v in raw.items()}

    channel = PushChannel(
        owner_id=current_user.id,
        name=data.name,
        type=data.type,
        config=encrypted,
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


def get_channel_config_plain(db, owner_id, channel_id) -> dict:
    """同步辅助: 读取并解密渠道配置 (供 /notifications/send 按渠道 id 发送使用)。

    注意: 此处为同步函数, 调用方需先异步取出 channel 对象。保留以便后续扩展。
    """
    return {}
