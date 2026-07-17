"""PushChannel 模型 (推送渠道配置)。对齐 PRD 6.6。"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ChannelType(str, enum.Enum):
    feishu = "feishu"
    wechat = "wechat"
    telegram = "telegram"
    hermes = "hermes"


class PushChannel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "push_channels"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[ChannelType] = mapped_column(Enum(ChannelType), nullable=False)
    # 加密存储的渠道配置: {webhook_url/bot_token/chat_id/channel} (敏感字段经 AES-256-GCM 加密)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)

    owner = relationship("User")
