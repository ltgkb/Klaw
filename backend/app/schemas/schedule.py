"""定时任务 Pydantic 模型。对齐 PRD 5.1。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.schedule_job import ScheduleStatus


class ScheduleCreate(BaseModel):
    """创建定时任务。"""
    flow_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    cron: str = Field(..., min_length=1, max_length=100, description="cron 表达式, 如 '0 9 * * *'")
    input: dict[str, Any] | None = None


class ScheduleUpdate(BaseModel):
    """更新定时任务。"""
    name: str | None = Field(None, min_length=1, max_length=200)
    cron: str | None = Field(None, min_length=1, max_length=100)
    input: dict[str, Any] | None = None
    status: ScheduleStatus | None = None


class ScheduleRead(BaseModel):
    """定时任务响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    flow_id: uuid.UUID
    name: str
    cron: str
    input: dict[str, Any] | None
    status: ScheduleStatus
    next_run_time: datetime | None
    apscheduler_job_id: str | None
    created_at: datetime
    updated_at: datetime
