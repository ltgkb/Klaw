"""推送通知端点。对齐 PRD M4 / 6.6。

- POST /notifications/send: 立即推送 (内联渠道 + 已配置渠道 id)
- 渠道配置管理见 /push/channels
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.core.notify_client import notify
from app.models.push_channel import PushChannel
from app.schemas.notification import NotifyChannelConfig, NotifyRequest, NotifyResponse, NotifyResult
from app.schemas.push_channel import SENSITIVE_CONFIG_KEYS
from app.utils.crypto import decrypt

logger = logging.getLogger("claw.notifications")

router = APIRouter(prefix="/notifications", tags=["推送通知"])


@router.post("/send", response_model=NotifyResponse)
async def send_notification(data: NotifyRequest, current_user: CurrentUser, db: DBSession):
    """立即推送消息到指定渠道。

    支持两种渠道来源:
      - channels: 内联渠道配置 (一次性)
      - channel_ids: 已持久化渠道 id (敏感字段自动解密解析为渠道配置)
    """
    channels_cfg = [ch.model_dump() for ch in data.channels]

    # 解析已持久化渠道 id
    if data.channel_ids:
        result = await db.execute(
            select(PushChannel).where(
                PushChannel.owner_id == current_user.id,
                PushChannel.id.in_(data.channel_ids),
            )
        )
        for ch in result.scalars().all():
            decrypted = {}
            decrypt_failed = False
            for k, v in (ch.config or {}).items():
                if k in SENSITIVE_CONFIG_KEYS and isinstance(v, str):
                    try:
                        decrypted[k] = decrypt(v)
                    except Exception:
                        # 解密失败 (密钥变更/数据损坏) → 记 warning 并跳过该渠道,
                        # 绝不把密文/原文当明文发出
                        logger.warning("渠道 %s 敏感字段 %s 解密失败, 跳过该渠道", ch.id, k)
                        decrypt_failed = True
                        break
                else:
                    decrypted[k] = v
            if decrypt_failed:
                continue
            decrypted["type"] = ch.type.value
            channels_cfg.append(decrypted)

    if not channels_cfg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未提供任何推送渠道 (channels / channel_ids)",
        )

    results = await notify(channels_cfg, data.title, data.content)
    return NotifyResponse(results=[NotifyResult(**r) for r in results])
