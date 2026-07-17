"""推送通知端点。对齐 PRD M4 / 6.6。

- POST /notifications/send: 立即推送 (内联渠道 + 已配置渠道 id)
- 渠道配置管理见 /push/channels
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession
from app.core.notify_client import notify
from app.models.push_channel import PushChannel
from app.schemas.notification import NotifyChannelConfig, NotifyRequest, NotifyResponse, NotifyResult
from app.utils.crypto import decrypt

router = APIRouter(prefix="/notifications", tags=["推送通知"])


@router.post("/send", response_model=NotifyResponse)
async def send_notification(data: NotifyRequest, current_user: CurrentUser, db: DBSession):
    """立即推送消息到指定渠道。

    支持两种渠道来源:
      - channels: 内联渠道配置 (一次性)
      - channel_ids: 已持久化渠道 id (自动解密解析为渠道配置)
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
            for k, v in (ch.config or {}).items():
                try:
                    decrypted[k] = decrypt(v) if isinstance(v, str) else v
                except Exception:
                    decrypted[k] = v
            decrypted["type"] = ch.type.value
            channels_cfg.append(decrypted)

    if not channels_cfg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未提供任何推送渠道 (channels / channel_ids)",
        )

    results = await notify(channels_cfg, data.title, data.content)
    return NotifyResponse(results=[NotifyResult(**r) for r in results])
