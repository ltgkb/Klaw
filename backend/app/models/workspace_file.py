"""WorkspaceFile 模型 (用户文件工作区)。对齐 PRD 5.1 / 6.7。"""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class WorkspaceFile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspace_files"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    object_name: Mapped[str] = mapped_column(String(1024), nullable=False)  # MinIO 对象路径
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False, default="application/octet-stream")

    # 关系
    owner = relationship("User")
