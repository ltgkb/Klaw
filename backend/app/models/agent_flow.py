"""AgentFlow 模型 (画布工作流)。对齐 PRD 5.1。"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class FlowStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class TriggerType(str, enum.Enum):
    manual = "manual"
    scheduled = "scheduled"
    webhook = "webhook"


class AgentFlow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_flows"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # DAG: {nodes:[{id,type,position,data}], edges:[{source,target,condition}]}
    dag: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[FlowStatus] = mapped_column(
        Enum(FlowStatus), default=FlowStatus.draft, nullable=False
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        Enum(TriggerType), default=TriggerType.manual, nullable=False
    )
    trigger_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 关系
    owner = relationship("User", back_populates="flows")
    executions = relationship("Execution", back_populates="flow", cascade="all, delete-orphan")
