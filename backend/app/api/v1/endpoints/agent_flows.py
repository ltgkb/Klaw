"""Agent 工作流端点。对齐 PRD 6.2 Agent 画布 API。

完整 CRUD + 执行触发 + SSE 实时状态。
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.core.deps import CurrentUser, DBSession
from app.core.security import decode_token
from app.models.user import User
from app.schemas.agent_flow import (
    ExecuteRequest,
    ExecuteResponse,
    ExecutionRead,
    FlowCreate,
    FlowRead,
    FlowUpdate,
)
from app.schemas.common import PageResponse
from app.services import agent_flow_service, execution_service

router = APIRouter(prefix="/agent-flows", tags=["Agent 画布"])


# ── 工作流 CRUD ──

@router.post("", response_model=FlowRead, status_code=status.HTTP_201_CREATED)
async def create_flow(data: FlowCreate, current_user: CurrentUser, db: DBSession):
    """创建工作流。"""
    flow = await agent_flow_service.create_flow(db, current_user.id, data)
    return FlowRead.model_validate(flow)


@router.get("", response_model=PageResponse[FlowRead])
async def list_flows(
    current_user: CurrentUser,
    db: DBSession,
    page: int = 1,
    page_size: int = 20,
):
    """列出当前用户的工作流。"""
    items, total = await agent_flow_service.list_flows(db, current_user.id, page, page_size)
    return PageResponse(
        items=[FlowRead.model_validate(f) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{flow_id}", response_model=FlowRead)
async def get_flow(flow_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """获取工作流详情。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    return FlowRead.model_validate(flow)


@router.put("/{flow_id}", response_model=FlowRead)
async def update_flow(flow_id: uuid.UUID, data: FlowUpdate, current_user: CurrentUser, db: DBSession):
    """更新工作流 (含保存 DAG)。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    flow = await agent_flow_service.update_flow(db, flow, data)
    return FlowRead.model_validate(flow)


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow(flow_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """删除工作流。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    await agent_flow_service.delete_flow(db, flow)


# ── 执行 ──

@router.post("/{flow_id}/execute", response_model=ExecuteResponse, status_code=status.HTTP_201_CREATED)
async def execute_flow(
    flow_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DBSession,
    data: ExecuteRequest | None = None,
):
    """触发工作流执行 (后台异步)。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")

    input_data = data.input if data else {}
    execution = await agent_flow_service.create_execution(db, flow_id, input_data)

    # 后台异步执行
    background_tasks.add_task(execution_service.run_flow, execution.id, flow_id)

    return ExecuteResponse(
        execution_id=execution.id,
        flow_id=flow_id,
        status=execution.status,
    )


@router.get("/{flow_id}/executions", response_model=list[ExecutionRead])
async def list_executions(flow_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """列出工作流的执行历史。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    executions = await agent_flow_service.list_executions(db, flow_id)
    return [ExecutionRead.model_validate(e) for e in executions]


@router.get("/{flow_id}/executions/{execution_id}", response_model=ExecutionRead)
async def get_execution(
    flow_id: uuid.UUID,
    execution_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """获取执行详情。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    execution = await agent_flow_service.get_execution(db, execution_id)
    if execution is None or execution.flow_id != flow_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    return ExecutionRead.model_validate(execution)


# ── 人机交互: 暂停/恢复/取消 ──

@router.post("/{flow_id}/executions/{execution_id}/pause", response_model=ExecutionRead)
async def pause_execution(
    flow_id: uuid.UUID,
    execution_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """暂停执行 (在下一个节点前生效)。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    ok = await execution_service.pause_execution(db, execution_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法暂停 (执行可能已结束)")
    execution = await agent_flow_service.get_execution(db, execution_id)
    return ExecutionRead.model_validate(execution)


@router.post("/{flow_id}/executions/{execution_id}/resume", response_model=ExecutionRead)
async def resume_execution(
    flow_id: uuid.UUID,
    execution_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """恢复暂停的执行。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    ok = await execution_service.resume_execution(db, execution_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法恢复 (执行可能未暂停)")
    execution = await agent_flow_service.get_execution(db, execution_id)
    return ExecutionRead.model_validate(execution)


@router.post("/{flow_id}/executions/{execution_id}/cancel", response_model=ExecutionRead)
async def cancel_execution(
    flow_id: uuid.UUID,
    execution_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """取消执行。"""
    flow = await agent_flow_service.get_flow(db, flow_id, current_user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    ok = await execution_service.cancel_execution(db, execution_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法取消 (执行可能已结束)")
    execution = await agent_flow_service.get_execution(db, execution_id)
    return ExecutionRead.model_validate(execution)


@router.get("/{flow_id}/executions/{execution_id}/stream")
async def stream_execution(
    flow_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: DBSession,
    token: str | None = Query(None, description="JWT access token (EventSource 无法设置 Header, 通过 query 传递)"),
):
    """SSE 实时推送执行状态。

    事件类型:
      - progress: 节点状态更新 (node_states)
      - complete: 执行完成 (最终状态)

    认证: 浏览器 EventSource 不支持自定义 Header, 因此通过 ?token= 查询参数传递 JWT。
    """
    # 鉴权: token 可从 query 参数或 Authorization header 获取
    user = None
    if token:
        payload = decode_token(token)
        if payload and payload.get("type") == "access":
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
                user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未认证")

    flow = await agent_flow_service.get_flow(db, flow_id, user.id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")

    async def event_generator():
        while True:
            execution = await agent_flow_service.get_execution(db, execution_id)
            if execution is None:
                yield {"event": "error", "data": json.dumps({"error": "执行记录不存在"})}
                break

            payload = {
                "execution_id": str(execution.id),
                "status": execution.status.value if hasattr(execution.status, "value") else str(execution.status),
                "node_states": execution.node_states or {},
                "output": execution.output,
                "error_message": execution.error_message,
            }

            if execution.status in (
                "success",
                "failed",
                "cancelled",
            ) or (
                hasattr(execution.status, "value")
                and execution.status.value in ("success", "failed", "cancelled")
            ):
                yield {"event": "complete", "data": json.dumps(payload, ensure_ascii=False, default=str)}
                break

            yield {"event": "progress", "data": json.dumps(payload, ensure_ascii=False, default=str)}
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())
