"""Resolve owner-scoped push channels for API and workflow delivery."""

import logging
import uuid

from sqlalchemy import select

from app.models.push_channel import PushChannel
from app.schemas.push_channel import SENSITIVE_CONFIG_KEYS
from app.utils.crypto import decrypt

logger = logging.getLogger("claw.push_channels")


async def resolve_channel_configs(
    db,
    owner_id: uuid.UUID,
    channel_ids: list[uuid.UUID | str],
    *,
    skip_unusable: bool = False,
) -> list[dict]:
    """Load, owner-check and decrypt saved channels while preserving input order."""
    normalized: list[uuid.UUID] = []
    for raw_id in channel_ids:
        try:
            channel_id = raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))
        except (TypeError, ValueError, AttributeError) as exc:
            if skip_unusable:
                logger.warning("忽略格式无效的推送渠道 id")
                continue
            raise ValueError("推送渠道不存在或无权访问") from exc
        if channel_id not in normalized:
            normalized.append(channel_id)

    if not normalized:
        return []

    result = await db.execute(
        select(PushChannel).where(
            PushChannel.owner_id == owner_id,
            PushChannel.id.in_(normalized),
        )
    )
    channels_by_id = {channel.id: channel for channel in result.scalars().all()}

    missing = [channel_id for channel_id in normalized if channel_id not in channels_by_id]
    if missing and not skip_unusable:
        raise ValueError("推送渠道不存在或无权访问")

    configs: list[dict] = []
    for channel_id in normalized:
        channel = channels_by_id.get(channel_id)
        if channel is None:
            continue
        config: dict = {}
        try:
            for key, value in (channel.config or {}).items():
                config[key] = (
                    decrypt(value)
                    if key in SENSITIVE_CONFIG_KEYS and isinstance(value, str)
                    else value
                )
        except Exception as exc:
            logger.warning("推送渠道 %s 解密失败", channel.id)
            if skip_unusable:
                continue
            raise ValueError("推送渠道配置无法解密，请在设置中重新配置") from exc
        config["type"] = channel.type.value
        configs.append(config)

    return configs
