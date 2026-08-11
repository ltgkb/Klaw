"""Agent 工作流端点。对齐 PRD 6.2 Agent 画布 API。

完整 CRUD + 执行触发 + SSE 实时状态。
"""

import asyncio
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
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
    execution = await _get_owned_execution(db, flow_id, execution_id, current_user.id)
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
    await _get_owned_execution(db, flow_id, execution_id, current_user.id)
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
    await _get_owned_execution(db, flow_id, execution_id, current_user.id)
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
    await _get_owned_execution(db, flow_id, execution_id, current_user.id)
    ok = await execution_service.cancel_execution(db, execution_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法取消 (执行可能已结束)")
    execution = await agent_flow_service.get_execution(db, execution_id)
    return ExecutionRead.model_validate(execution)


async def _get_owned_execution(db, flow_id, execution_id, owner_id):
    """Return an execution only when both its flow and execution belong together."""
    flow = await agent_flow_service.get_flow(db, flow_id, owner_id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")

    execution = await agent_flow_service.get_execution(db, execution_id)
    if execution is None or execution.flow_id != flow_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="执行记录不存在")
    return execution


@router.get("/{flow_id}/executions/{execution_id}/stream")
async def stream_execution(
    flow_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: DBSession,
    authorization: str | None = Header(None),
):
    """SSE 实时推送执行状态。

    事件类型:
      - progress: 节点状态更新 (node_states)
      - complete: 执行完成 (最终状态)

    认证: 仅使用 Authorization Bearer Header，避免 JWT 出现在 URL/访问日志中。
    """
    bearer_token = None
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            bearer_token = credentials

    access_token = bearer_token
    payload = decode_token(access_token) if access_token else None
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的认证令牌")

    try:
        user_id = uuid.UUID(payload.get("sub", ""))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效令牌") from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户已被禁用")

    # 越权校验: execution 必须属于该 flow 且 flow 属于当前用户;
    # 不存在/跨 flow/越权统一 404, 不泄漏他人执行记录的存在性
    await _get_owned_execution(db, flow_id, execution_id, user.id)

    async def event_generator():
        while True:
            execution = await agent_flow_service.get_execution(db, execution_id)
            if execution is None:
                yield {"event": "error", "data": json.dumps({"error": "执行记录不存在"})}
                break
            # The executor commits through a separate session. Refresh the
            # identity-mapped row so a stream opened while pending can observe it.
            await db.refresh(execution)

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
