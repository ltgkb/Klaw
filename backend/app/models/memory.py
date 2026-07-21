"""Memory 模型 (本地持久记忆)。对齐 PRD 5.1。

短期记忆存 Redis，长期/工作区记忆存 PostgreSQL (本表)。
"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class MemoryType(str, enum.Enum):
    preference = "preference"
    decision = "decision"
    context = "context"


class Memory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memories"
    # 同 user + key + session 唯一: save_memory 走 upsert, 并发冲突转 update
    __table_args__ = (
        UniqueConstraint("user_id", "key", "session_id", name="uq_memories_user_key_session"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[MemoryType] = mapped_column(
        Enum(MemoryType), default=MemoryType.context, nullable=False
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
