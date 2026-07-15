"""Agent 工作流 CRUD 业务逻辑。对齐 PRD 5.1 / 6.2。"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_flow import AgentFlow
from app.models.execution import Execution
from app.schemas.agent_flow import FlowCreate, FlowUpdate

logger = logging.getLogger("claw.flow_service")


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
    """删除工作流及其执行记录 (cascade)。"""
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
    """列出工作流的执行记录。"""
    result = await db.execute(
        select(Execution).where(Execution.flow_id == flow_id).order_by(Execution.created_at.desc())
    )
    return list(result.scalars().all())


async def get_execution(db: AsyncSession, execution_id) -> Execution | None:
    """获取执行记录。"""
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    return result.scalar_one_or_none()
