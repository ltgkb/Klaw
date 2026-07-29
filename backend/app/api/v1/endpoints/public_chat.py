"""Anonymous chat endpoint used by the public KAI homepage."""

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from opencc import OpenCC
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
from app.models.execution import ExecutionStatus
from app.models.knowledge_base import KnowledgeBase
from app.services import agent_flow_service, execution_service

router = APIRouter(prefix="/public-chat", tags=["公开智能问答"])
traditional_converter = OpenCC("s2twp")
CONTACT_FOOTER = "想了解更具体的信息请联系\n+86 13256083619\n2291169018@qq.com\n王经理"
UNCERTAIN_SECTION_MARKERS = (
    "还需要界定的范围是",
    "還需要界定的範圍是",
    "待确认事项",
    "待確認事項",
    "尚待明确",
    "尚待明確",
    "仍待明确",
    "仍待明確",
    "仍需确认",
    "仍需確認",
    "需要确认的边界",
    "需要確認的邊界",
    "确认的边界",
    "確認的邊界",
    "确认范围",
    "確認範圍",
    "matters to be confirmed",
    "scope still to be defined",
)


class PublicChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None
    language: Literal["zh-TW", "en", "zh-CN"] = "zh-TW"


class PublicChatResponse(BaseModel):
    answer: str
    conversation_id: uuid.UUID
    execution_id: uuid.UUID
    created_at: datetime


class PublicKnowledgeBaseItem(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    embedding_model: str
    chunk_strategy: str
    document_count: int
    status: str


class PublicFlowItem(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    node_count: int
    status: str


class PublicCatalogResponse(BaseModel):
    knowledge_bases: list[PublicKnowledgeBaseItem]
    flows: list[PublicFlowItem]


def _no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _configured_flow_id() -> uuid.UUID:
    try:
        return uuid.UUID(settings.public_chat_flow_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=503, detail="公开问答工作流未配置") from None


def _format_public_answer(answer: str) -> str:
    """Remove internal-style uncertainty sections and append the contact footer once."""
    blocks = re.split(r"\n\s*\n", answer.strip())
    filtered: list[str] = []
    skip_explanation = False
    for block in blocks:
        normalized = re.sub(r"\s+", "", block).lower()
        if any(re.sub(r"\s+", "", marker).lower() in normalized for marker in UNCERTAIN_SECTION_MARKERS):
            skip_explanation = len(block.strip()) < 80
            continue
        if skip_explanation:
            skip_explanation = False
            continue
        filtered.append(block.strip())

    cleaned = "\n\n".join(block for block in filtered if block).strip()
    if "13256083619" in cleaned or "2291169018@qq.com" in cleaned:
        return cleaned
    return f"{cleaned}\n\n{CONTACT_FOOTER}" if cleaned else CONTACT_FOOTER


@router.get("/catalog", response_model=PublicCatalogResponse)
async def public_catalog(response: Response, db: DBSession):
    """Expose a read-only, sanitized catalog for visitors."""
    _no_cache(response)
    knowledge_bases = (
        await db.execute(select(KnowledgeBase).order_by(KnowledgeBase.updated_at.desc()))
    ).scalars().all()
    flows = (
        await db.execute(select(AgentFlow).order_by(AgentFlow.updated_at.desc()))
    ).scalars().all()
    return PublicCatalogResponse(
        knowledge_bases=[
            PublicKnowledgeBaseItem(
                id=kb.id,
                name=kb.name,
                description=kb.description,
                embedding_model=kb.embedding_model,
                chunk_strategy=kb.chunk_strategy.value,
                document_count=kb.document_count,
                status=kb.status.value,
            )
            for kb in knowledge_bases
        ],
        flows=[
            PublicFlowItem(
                id=flow.id,
                name=flow.name,
                description=flow.description,
                node_count=len((flow.dag or {}).get("nodes", [])),
                status=flow.status.value,
            )
            for flow in flows
        ],
    )


@router.post("", response_model=PublicChatResponse)
async def public_chat(data: PublicChatRequest, response: Response, db: DBSession):
    """Run the configured KAI platform Q&A flow without requiring login."""
    _no_cache(response)
    flow_id = _configured_flow_id()
    flow = (
        await db.execute(select(AgentFlow).where(AgentFlow.id == flow_id))
    ).scalar_one_or_none()
    if flow is None:
        raise HTTPException(status_code=503, detail="公开问答工作流不存在")

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
        conversation = Conversation(
            flow_id=flow.id,
            owner_id=flow.owner_id,
            title=data.message.strip().replace("\n", " ")[:50] or "公开问答",
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

    language_instructions = {
        "zh-TW": "請使用繁體中文回答。",
        "en": "Please answer in English.",
        "zh-CN": "请使用简体中文回答。",
    }
    exec_input = {
        "input": data.message,
        "sys.query": data.message,
        "sys.response_language": language_instructions[data.language],
        "history": history,
    }
    start_name = _first_start_input_name(flow.dag)
    if start_name:
        exec_input[start_name] = data.message
    execution = await agent_flow_service.create_execution(db, flow.id, exec_input)

    try:
        await asyncio.wait_for(
            execution_service.run_flow(execution.id, flow.id),
            timeout=settings.public_chat_timeout_seconds,
        )
    except TimeoutError:
        await db.refresh(execution)
        if execution.status in {ExecutionStatus.pending, ExecutionStatus.running}:
            execution.status = ExecutionStatus.failed
            execution.error_message = "公开问答请求超时"
            await db.commit()
        raise HTTPException(status_code=504, detail="回答超时，请稍后重试") from None

    await db.refresh(execution)
    if execution.status != ExecutionStatus.success:
        raise HTTPException(
            status_code=502,
            detail=execution.error_message or "问答工作流执行失败",
        )

    answer = _final_answer(execution)
    if data.language == "zh-TW":
        answer = traditional_converter.convert(answer)
    answer = _format_public_answer(answer)
    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.assistant,
            content=answer,
        )
    )
    await db.commit()

    return PublicChatResponse(
        answer=answer,
        conversation_id=conversation.id,
        execution_id=execution.id,
        created_at=datetime.now(timezone.utc),
    )
