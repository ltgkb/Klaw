"""KnowledgeBase 模型。对齐 PRD 5.1。"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ChunkStrategy(str, enum.Enum):
    semantic = "semantic"
    recursive = "recursive"
    fixed = "fixed"
    markdown = "markdown"


class KBStatus(str, enum.Enum):
    active = "active"
    indexing = "indexing"
    error = "error"


class KnowledgeBase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_bases"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(String(100), default="BGE-M3", nullable=False)
    chunk_strategy: Mapped[ChunkStrategy] = mapped_column(
        Enum(ChunkStrategy), default=ChunkStrategy.semantic, nullable=False
    )
    chunk_size: Mapped[int] = mapped_column(Integer, default=512, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    document_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[KBStatus] = mapped_column(
        Enum(KBStatus), default=KBStatus.active, nullable=False
    )

    # 关系
    owner = relationship("User", back_populates="knowledge_bases")
    documents = relationship("Document", back_populates="kb", cascade="all, delete-orphan")
