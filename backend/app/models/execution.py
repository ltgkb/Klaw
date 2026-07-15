"""Execution 模型 (工作流执行记录)。对齐 PRD 5.1。"""

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ExecutionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class Execution(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "executions"

    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_flows.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus), default=ExecutionStatus.pending, nullable=False
    )
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 每个节点的执行状态: {node_id: {status, output, started_at, ended_at}}
    node_states: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 关系
    flow = relationship("AgentFlow", back_populates="executions")
