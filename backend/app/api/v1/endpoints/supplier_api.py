"""Public, API-key protected customer-service endpoint for the supplier flow."""

import asyncio
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.endpoints.agent_chat import (
    _final_answer,
    _first_start_input_name,
    _format_history,
)
from app.core.config import settings
from app.core.deps import DBSession
from app.models.agent_flow import AgentFlow
from app.models.conversation import Conversation, Message, MessageRole
from app.models.execution import Execution, ExecutionStatus
from app.services import agent_flow_service, execution_service

router = APIRouter(prefix="/supplier-chat", tags=["供应商客服 API"])


class SupplierChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


class SupplierChatResponse(BaseModel):
    answer: str
    conversation_id: uuid.UUID
    execution_id: uuid.UUID
    created_at: datetime


def _cors(response: Response) -> None:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Cache-Control"] = "no-store"


def _check_key(x_api_key: str | None, authorization: str | None) -> None:
    supplied = x_api_key
    if not supplied and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            supplied = value
    if not settings.supplier_api_key or not supplied or not secrets.compare_digest(
        supplied, settings.supplier_api_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _configured_flow_id() -> uuid.UUID:
    try:
        return uuid.UUID(settings.supplier_flow_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="供应商客服工作流未配置",
        ) from None


@router.options("")
async def supplier_chat_options(response: Response):
    _cors(response)
    return Response(status_code=204, headers=response.headers)


@router.post("", response_model=SupplierChatResponse)
async def supplier_chat(
    data: SupplierChatRequest,
    response: Response,
    db: DBSession,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """Run the configured supplier flow synchronously and return its final answer."""
    _cors(response)
    _check_key(x_api_key, authorization)

    flow_id = _configured_flow_id()
    flow = (
        await db.execute(select(AgentFlow).where(AgentFlow.id == flow_id))
    ).scalar_one_or_none()
    if flow is None:
        raise HTTPException(status_code=503, detail="供应商客服工作流不存在")

    conversation = None
    if data.conversation_id:
        conversation = (
            await db.execute(
                select(Conversation).where(
                    Conversation.id == data.conversation_id,
                    Conversation.flow_id == flow.id,
                    Conversation.owner_id == flow.owner_id,
                )
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        conversation = Conversation(
            flow_id=flow.id,
            owner_id=flow.owner_id,
            title=data.message.strip().replace("\n", " ")[:50] or "网站客服",
        )
        db.add(conversation)
        await db.flush()

    prior = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at)
        )
    ).scalars().all()
    history = _format_history(prior)
    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.user,
            content=data.message,
        )
    )
    await db.commit()

    exec_input = {"input": data.message, "sys.query": data.message, "history": history}
    start_name = _first_start_input_name(flow.dag)
    if start_name:
        exec_input[start_name] = data.message
    execution = await agent_flow_service.create_execution(db, flow.id, exec_input)

    try:
        await asyncio.wait_for(
            execution_service.run_flow(execution.id, flow.id),
            timeout=settings.supplier_api_timeout_seconds,
        )
    except TimeoutError:
        await db.refresh(execution)
        if execution and execution.status in {ExecutionStatus.pending, ExecutionStatus.running}:
            execution.status = ExecutionStatus.failed
            execution.error_message = "供应商客服请求超时"
            await db.commit()
        raise HTTPException(status_code=504, detail="客服响应超时，请稍后重试") from None

    # run_flow uses its own DB session, so refresh the request-session identity
    # instead of reading the stale object already held in this session.
    await db.refresh(execution)
    if execution is None or execution.status != ExecutionStatus.success:
        detail = execution.error_message if execution else "执行记录不存在"
        raise HTTPException(status_code=502, detail=detail or "客服工作流执行失败")

    answer = _final_answer(execution)
    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.assistant,
            content=answer,
        )
    )
    await db.commit()

    return SupplierChatResponse(
        answer=answer,
        conversation_id=conversation.id,
        execution_id=execution.id,
        created_at=datetime.now(timezone.utc),
    )
