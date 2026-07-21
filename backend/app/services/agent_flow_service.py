"""Agent 工作流 CRUD 业务逻辑。对齐 PRD 5.1 / 6.2。"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_flow import AgentFlow
from app.models.execution import Execution, ExecutionStatus
from app.schemas.agent_flow import FlowCreate, FlowUpdate

logger = logging.getLogger("claw.flow_service")

# 惰性回收阈值: running/paused 超过该时长未更新即视为服务重启中断
STALE_EXECUTION_MINUTES = 30


async def _reap_stale_executions(db: AsyncSession, executions: list[Execution]) -> None:
    """惰性回收: list/get 执行时, 把 running/paused 且 updated_at 超 30 分钟的记录置 failed。

    服务重启后后台任务已丢失, DB 中的 running/paused 状态永远不会再推进,
    这里在读取路径上惰性修正, 避免引入额外的后台巡检 (不改 main.py)。
    """
    now = datetime.now(timezone.utc)
    reaped: list[Execution] = []
    for ex in executions:
        if ex.status not in (ExecutionStatus.running, ExecutionStatus.paused):
            continue
        updated = ex.updated_at
        if updated is None:
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if now - updated > timedelta(minutes=STALE_EXECUTION_MINUTES):
            ex.status = ExecutionStatus.failed
            ex.error_message = "服务重启中断"
            reaped.append(ex)
    if reaped:
        await db.commit()
        # commit 后 updated_at (onupdate=func.now()) 会被标记过期, 刷新以便调用方直接读取
        for ex in reaped:
            await db.refresh(ex)
        logger.info("惰性回收过期执行记录 %d 条", len(reaped))


async def create_flow(db: AsyncSession, owner_id, data: FlowCreate) -> AgentFlow:
    """创建工作流。"""
    flow = AgentFlow(
        name=data.name,
        description=data.description,
        owner_id=owner_id,
        dag=data.dag,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
    )
    db.add(flow)
    await db.commit()
    await db.refresh(flow)
    logger.info("工作流创建: %s (%s)", flow.name, flow.id)
    return flow


async def list_flows(db: AsyncSession, owner_id, page: int = 1, page_size: int = 20) -> tuple[list[AgentFlow], int]:
    """列出用户的工作流 (owner 隔离)。"""
    base_query = select(AgentFlow).where(AgentFlow.owner_id == owner_id)
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(
        base_query.order_by(AgentFlow.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return items, total


async def get_flow(db: AsyncSession, flow_id, owner_id) -> AgentFlow | None:
    """获取工作流 (owner 隔离)。"""
    result = await db.execute(
        select(AgentFlow).where(AgentFlow.id == flow_id, AgentFlow.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def get_flow_no_owner_check(db: AsyncSession, flow_id) -> AgentFlow | None:
    """获取工作流 (不检查 owner, 内部使用)。"""
    result = await db.execute(select(AgentFlow).where(AgentFlow.id == flow_id))
    return result.scalar_one_or_none()


async def update_flow(db: AsyncSession, flow: AgentFlow, data: FlowUpdate) -> AgentFlow:
    """更新工作流。"""
    if data.name is not None:
        flow.name = data.name
    if data.description is not None:
        flow.description = data.description
    if data.dag is not None:
        flow.dag = data.dag
    if data.status is not None:
        flow.status = data.status
    if data.trigger_type is not None:
        flow.trigger_type = data.trigger_type
    if data.trigger_config is not None:
        flow.trigger_config = data.trigger_config
    await db.commit()
    await db.refresh(flow)
    return flow


async def delete_flow(db: AsyncSession, flow: AgentFlow) -> None:
    """删除工作流及其执行记录 (cascade); 删除前摘除关联的定时任务 (契约3)。"""
    from app.core import scheduler as scheduler_module
    from app.models.schedule_job import ScheduleJob

    jobs_result = await db.execute(select(ScheduleJob).where(ScheduleJob.flow_id == flow.id))
    for job in jobs_result.scalars().all():
        scheduler_module.unschedule_flow(str(job.id))

    await db.delete(flow)
    await db.commit()
    logger.info("工作流删除: %s", flow.id)


# ── 执行记录 ──

async def create_execution(db: AsyncSession, flow_id, input_data: dict | None = None) -> Execution:
    """创建执行记录。"""
    execution = Execution(
        flow_id=flow_id,
        status="pending",
        input=input_data,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    logger.info("执行记录创建: flow=%s execution=%s", flow_id, execution.id)
    return execution


async def list_executions(db: AsyncSession, flow_id) -> list[Execution]:
    """列出工作流的执行记录 (惰性回收过期 running/paused)。"""
    result = await db.execute(
        select(Execution).where(Execution.flow_id == flow_id).order_by(Execution.created_at.desc())
    )
    executions = list(result.scalars().all())
    await _reap_stale_executions(db, executions)
    return executions


async def get_execution(db: AsyncSession, execution_id) -> Execution | None:
    """获取执行记录 (惰性回收过期 running/paused)。"""
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if execution is not None:
        await _reap_stale_executions(db, [execution])
    return execution
