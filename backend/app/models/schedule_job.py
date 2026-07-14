"""ScheduleJob 模型 (APScheduler 持久化的定时任务)。对齐 PRD 5.1。

注: APScheduler 自身用 SQLAlchemyJobStore 管理 job 持久化 (存在独立的 apscheduler 表)，
本表是平台层面的任务元数据视图，记录 flow_id 关联与用户可见的调度信息。
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ScheduleStatus(str, enum.Enum):
    active = "active"
    paused = "paused"


class ScheduleJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "schedule_jobs"

    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_flows.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    cron: Mapped[str] = mapped_column(String(100), nullable=False)  # cron 表达式
    input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus), default=ScheduleStatus.active, nullable=False
    )
    next_run_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 对应 APScheduler 的 job id，用于联动
    apscheduler_job_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
