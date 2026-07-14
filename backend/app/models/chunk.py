"""Chunk 模型。对齐 PRD 5.1。"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ContentType(str, enum.Enum):
    text = "text"
    table = "table"
    image = "image"


class Chunk(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "chunks"

    doc_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[ContentType] = mapped_column(
        Enum(ContentType), default=ContentType.text, nullable=False
    )
    page: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 向量存储在 ES，这里不直接存 pgvector，仅记录 chunk 索引位置
    embedding_stored: Mapped[bool] = mapped_column(default=False, nullable=False)
    # 元数据: 来源文档、段落坐标等 ("metadata" 是 SQLAlchemy 保留属性名)
    chunk_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # 关系
    document = relationship("Document", back_populates="chunks")
