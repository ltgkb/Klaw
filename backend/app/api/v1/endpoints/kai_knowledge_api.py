"""API-key protected KAI knowledge customer-service endpoints."""

import asyncio
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.api.v1.endpoints.agent_chat import (
    _final_answer,
    _first_start_input_name,
    _format_history,
)
from app.api.v1.endpoints.public_chat import _format_public_answer, traditional_converter
from app.core.config import settings
from app.core.deps import DBSession
from app.models.agent_flow import AgentFlow
from app.models.conversation import Conversation, Message, MessageRole
from app.models.execution import ExecutionStatus
from app.services import agent_flow_service, execution_service

router = APIRouter(prefix="/kai-knowledge", tags=["KAI 知识客服 API"])


class KAIKnowledgeRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    language: Literal["zh-TW", "zh-CN", "en"] = "zh-TW"


class KAIKnowledgeResponse(BaseModel):
    answer: str
    conversation_id: uuid.UUID
    execution_id: uuid.UUID
    elapsed_seconds: float
    created_at: datetime


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Cache-Control": "no-store",
    }


def _check_key(x_api_key: str | None, authorization: str | None) -> None:
    supplied = x_api_key
    if not supplied and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            supplied = value
    configured = settings.kai_knowledge_api_key
    if not configured or not supplied or not secrets.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _flow_id() -> uuid.UUID:
    try:
        return uuid.UUID(settings.kai_knowledge_flow_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=503, detail="KAI 知识问答工作流未配置") from None


def _language_instruction(language: str) -> str:
    return {
        "zh-TW": "請使用繁體中文回答。",
        "zh-CN": "请使用简体中文回答。",
        "en": "Please answer in English.",
    }[language]


def _finalize_answer(execution, language: str) -> str:
    answer = _final_answer(execution)
    if language == "zh-TW":
        answer = traditional_converter.convert(answer)
    return _format_public_answer(answer)


async def _prepare(data: KAIKnowledgeRequest, db):
    flow = (
        await db.execute(select(AgentFlow).where(AgentFlow.id == _flow_id()))
    ).scalar_one_or_none()
    if flow is None:
        raise HTTPException(status_code=503, detail="KAI 知识问答工作流不存在")

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
            title=data.message.strip().replace("\n", " ")[:50] or "KAI 知识客服",
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
    db.add(Message(conversation_id=conversation.id, role=MessageRole.user, content=data.message))
    await db.commit()

    exec_input = {
        "input": data.message,
        "sys.query": data.message,
        "sys.response_language": _language_instruction(data.language),
        "history": history,
    }
    start_name = _first_start_input_name(flow.dag)
    if start_name:
        exec_input[start_name] = data.message
    execution = await agent_flow_service.create_execution(db, flow.id, exec_input)
    return flow, conversation, execution


async def _save_answer(db, conversation, answer: str) -> None:
    db.add(Message(conversation_id=conversation.id, role=MessageRole.assistant, content=answer))
    await db.commit()


@router.options("/chat")
@router.options("/chat/stream")
async def kai_knowledge_options():
    return Response(status_code=204, headers=_cors_headers())


@router.post("/chat", response_model=KAIKnowledgeResponse)
async def kai_knowledge_chat(
    data: KAIKnowledgeRequest,
    db: DBSession,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """Synchronous KAI knowledge question-answering API."""
    _check_key(x_api_key, authorization)
    flow, conversation, execution = await _prepare(data, db)
    started = asyncio.get_running_loop().time()
    try:
        await asyncio.wait_for(
            execution_service.run_flow(execution.id, flow.id),
            timeout=settings.kai_knowledge_api_timeout_seconds,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="KAI 知识问答超时，请稍后重试") from None

    await db.refresh(execution)
    if execution.status != ExecutionStatus.success:
        raise HTTPException(status_code=502, detail=execution.error_message or "KAI 知识问答执行失败")
    answer = _finalize_answer(execution, data.language)
    await _save_answer(db, conversation, answer)
    elapsed = asyncio.get_running_loop().time() - started
    return Response(
        content=KAIKnowledgeResponse(
            answer=answer,
            conversation_id=conversation.id,
            execution_id=execution.id,
            elapsed_seconds=round(elapsed, 2),
            created_at=datetime.now(timezone.utc),
        ).model_dump_json(),
        media_type="application/json",
        headers=_cors_headers(),
    )


@router.post("/chat/stream")
async def kai_knowledge_chat_stream(
    data: KAIKnowledgeRequest,
    db: DBSession,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
):
    """SSE API that reports retrieval progress and emits the final answer in chunks."""
    _check_key(x_api_key, authorization)
    flow, conversation, execution = await _prepare(data, db)

    async def events():
        started = asyncio.get_running_loop().time()
        task = asyncio.create_task(execution_service.run_flow(execution.id, flow.id))
        while not task.done():
            elapsed = asyncio.get_running_loop().time() - started
            if elapsed >= settings.kai_knowledge_api_timeout_seconds:
                task.cancel()
                yield {"event": "error", "data": json.dumps({"detail": "KAI 知识问答超时"}, ensure_ascii=False)}
                return
            yield {
                "event": "status",
                "data": json.dumps(
                    {"status": "retrieving", "elapsed_seconds": round(elapsed, 1)},
                    ensure_ascii=False,
                ),
            }
            await asyncio.sleep(1)

        try:
            await task
        except Exception as exc:
            yield {"event": "error", "data": json.dumps({"detail": str(exc)}, ensure_ascii=False)}
            return

        await db.refresh(execution)
        if execution.status != ExecutionStatus.success:
            yield {
                "event": "error",
                "data": json.dumps(
                    {"detail": execution.error_message or "KAI 知识问答执行失败"},
                    ensure_ascii=False,
                ),
            }
            return

        answer = _finalize_answer(execution, data.language)
        await _save_answer(db, conversation, answer)
        for offset in range(0, len(answer), 18):
            yield {
                "event": "delta",
                "data": json.dumps({"content": answer[offset : offset + 18]}, ensure_ascii=False),
            }
            await asyncio.sleep(0.02)
        elapsed = asyncio.get_running_loop().time() - started
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "conversation_id": str(conversation.id),
                    "execution_id": str(execution.id),
                    "elapsed_seconds": round(elapsed, 2),
                },
                ensure_ascii=False,
            ),
        }

    return EventSourceResponse(events(), headers=_cors_headers())
