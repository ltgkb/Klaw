"""定时任务 Pydantic 模型。对齐 PRD 5.1。"""

import uuid
from datetime import datetime
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.schedule_job import ScheduleStatus

_CRON_FIELDS = ("minute", "hour", "day", "month", "day_of_week")


def _validate_cron(v: str | None) -> str | None:
    """校验 cron 表达式: 必须 5 段且能被 APScheduler CronTrigger 解析。"""
    if v is None:
        return v
    parts = v.split()
    if len(parts) != 5:
        raise ValueError("cron 表达式必须包含 5 个字段 (分 时 日 月 周)")
    try:
        CronTrigger(**dict(zip(_CRON_FIELDS, parts)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无效的 cron 表达式: {v}") from exc
    return v


class ScheduleCreate(BaseModel):
    """创建定时任务。"""
    flow_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=200)
    cron: str = Field(..., min_length=1, max_length=100, description="cron 表达式, 如 '0 9 * * *'")
    input: dict[str, Any] | None = None

    _check_cron = field_validator("cron")(_validate_cron)


class ScheduleUpdate(BaseModel):
    """更新定时任务。"""
    name: str | None = Field(None, min_length=1, max_length=200)
    cron: str | None = Field(None, min_length=1, max_length=100)
    input: dict[str, Any] | None = None
    status: ScheduleStatus | None = None

    _check_cron = field_validator("cron")(_validate_cron)


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
