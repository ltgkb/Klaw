"""Document 模型。对齐 PRD 5.1。"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ParseStatus(str, enum.Enum):
    pending = "pending"
    parsing = "parsing"
    parsed = "parsed"
    failed = "failed"


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    kb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # MinIO URL
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parse_status: Mapped[ParseStatus] = mapped_column(
        Enum(ParseStatus), default=ParseStatus.pending, nullable=False
    )
    # DeepDoc 解析结果: {text, tables:[{html, page}], images:[{path, page, ocr_text}]}
    parse_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    @property
    def parse_error(self) -> str | None:
        """Return the persisted ingestion error without exposing parse internals."""
        if not isinstance(self.parse_result, dict):
            return None
        error = self.parse_result.get("error")
        return str(error) if error else None

    # 关系
    kb = relationship("KnowledgeBase", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
