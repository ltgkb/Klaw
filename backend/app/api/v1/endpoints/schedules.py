"""定时任务端点。对齐 PRD 5.1 / M4。"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DBSession
from app.core import scheduler as scheduler_module
from app.models.agent_flow import AgentFlow
from app.models.schedule_job import ScheduleJob, ScheduleStatus
from app.schemas.schedule import ScheduleCreate, ScheduleRead, ScheduleUpdate
from app.services import agent_flow_service

router = APIRouter(prefix="/schedules", tags=["定时任务"])


@router.post("", response_model=ScheduleRead, status_code=status.HTTP_201_CREATED)
async def create_schedule(data: ScheduleCreate, current_user: CurrentUser, db: DBSession):
    """创建定时任务。"""
    # 验证 flow 属于当前用户
    flow = await agent_flow_service.get_flow(db, data.flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")

    # 写入 DB
    job = ScheduleJob(
        flow_id=data.flow_id,
        name=data.name,
        cron=data.cron,
        input=data.input,
        status=ScheduleStatus.active,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # 注册到 APScheduler
    next_run = scheduler_module.schedule_flow(
        job_id=str(job.id),
        flow_id=data.flow_id,
        cron=data.cron,
        input_data=data.input,
        name=data.name,
    )
    job.apscheduler_job_id = str(job.id)
    job.next_run_time = next_run
    await db.commit()
    await db.refresh(job)

    return ScheduleRead.model_validate(job)


@router.get("", response_model=list[ScheduleRead])
async def list_schedules(
    current_user: CurrentUser,
    db: DBSession,
    status_filter: ScheduleStatus | None = Query(None, alias="status"),
):
    """列出当前用户的定时任务。"""
    # 查询用户所有 flow 的 id
    flows_result = await db.execute(
        select(AgentFlow.id).where(AgentFlow.owner_id == current_user.id)
    )
    flow_ids = [row[0] for row in flows_result.all()]
    if not flow_ids:
        return []

    query = select(ScheduleJob).where(ScheduleJob.flow_id.in_(flow_ids))
    if status_filter:
        query = query.where(ScheduleJob.status == status_filter)
    query = query.order_by(ScheduleJob.created_at.desc())
    result = await db.execute(query)
    return [ScheduleRead.model_validate(j) for j in result.scalars().all()]


@router.get("/{schedule_id}", response_model=ScheduleRead)
async def get_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """获取定时任务详情。"""
    result = await db.execute(select(ScheduleJob).where(ScheduleJob.id == schedule_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    # 验证所属 flow 属于当前用户
    flow = await agent_flow_service.get_flow(db, job.flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    return ScheduleRead.model_validate(job)


@router.put("/{schedule_id}", response_model=ScheduleRead)
async def update_schedule(schedule_id: uuid.UUID, data: ScheduleUpdate, current_user: CurrentUser, db: DBSession):
    """更新定时任务 (暂停/恢复/改 cron)。"""
    result = await db.execute(select(ScheduleJob).where(ScheduleJob.id == schedule_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    flow = await agent_flow_service.get_flow(db, job.flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")

    changed = False
    if data.name is not None:
        job.name = data.name
        changed = True
    if data.cron is not None:
        job.cron = data.cron
        changed = True
    if data.input is not None:
        job.input = data.input

    if data.status is not None:
        job.status = data.status
        if data.status == ScheduleStatus.paused:
            scheduler_module.pause_scheduled_job(str(job.id))
        elif data.status == ScheduleStatus.active:
            next_run = scheduler_module.resume_scheduled_job(str(job.id))
            job.next_run_time = next_run

    # 如果 cron 或 name 变了, 重新注册 APScheduler job
    if changed and job.status == ScheduleStatus.active:
        next_run = scheduler_module.schedule_flow(
            job_id=str(job.id),
            flow_id=job.flow_id,
            cron=job.cron,
            input_data=job.input,
            name=job.name,
        )
        job.next_run_time = next_run

    await db.commit()
    await db.refresh(job)
    return ScheduleRead.model_validate(job)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """删除定时任务。"""
    result = await db.execute(select(ScheduleJob).where(ScheduleJob.id == schedule_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")
    flow = await agent_flow_service.get_flow(db, job.flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="定时任务不存在")

    scheduler_module.unschedule_flow(str(job.id))
    await db.delete(job)
    await db.commit()
