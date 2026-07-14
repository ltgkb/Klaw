"""User 模型。对齐 PRD 5.1。"""

import enum

from sqlalchemy import JSON, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"
    viewer = "viewer"


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.user, nullable=False
    )
    # 本地 Agent 配置 (OpenClaw/Hermes 连接参数等)
    openclaw_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # OpenAI API Key — AES-256-GCM 加密存储 (PRD 8.2)
    openai_api_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 标记 openai_api_key 是否已加密
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # 关系
    knowledge_bases = relationship("KnowledgeBase", back_populates="owner", cascade="all, delete-orphan")
    flows = relationship("AgentFlow", back_populates="owner", cascade="all, delete-orphan")
