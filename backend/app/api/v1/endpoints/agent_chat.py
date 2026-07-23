"""对话式 Agent 端点。把工作流当作聊天助手运行: 用户消息 → {sys.query}/{input}, 多轮历史 → {history}。

- GET  /agent-flows/{flow_id}/chat/conversations : 会话列表
- POST /agent-flows/{flow_id}/chat/conversations : 新建会话
- DELETE /agent-flows/{flow_id}/chat/conversations/{conversation_id} : 删除会话
- GET  /agent-flows/{flow_id}/chat/messages : 指定会话的消息历史
- POST /agent-flows/{flow_id}/chat          : 触发一轮对话 (异步执行, 返回 execution_id); 前端轮询消息获取回答
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.deps import CurrentUser, DBSession
from app.models.agent_flow import AgentFlow
from app.models.conversation import Conversation, Message, MessageRole
from app.models.execution import Execution, ExecutionStatus
from app.schemas.conversation import ChatRequest, ChatResponse, ConversationRead, MessageRead
from app.services import agent_flow_service, execution_service

logger = logging.getLogger("claw.agent_chat")

router = APIRouter(prefix="/agent-flows", tags=["对话式 Agent"])

# 持有后台任务引用, 防止事件循环在任务完成前将其 GC 掉
_background_tasks: set[asyncio.Task] = set()


def _final_answer(execution: Execution) -> str:
    """从执行结果提取最终回答: 优先 end 节点输出, 否则最后一个节点输出。"""
    if execution.status == ExecutionStatus.failed:
        return execution.error_message or "(执行失败)"
    if execution.status == ExecutionStatus.cancelled:
        return execution.error_message or "(执行已取消)"
    node_states = execution.node_states or {}
    for st in node_states.values():
        if st.get("type") == "end":
            return str(st.get("output") or "")
    out = execution.output or {}
    if out:
        last = next(reversed(out))
        return str(out[last] or "")
    return execution.error_message or "(无输出)"


async def _get_owned_flow(db: AsyncSession, flow_id, owner_id) -> AgentFlow:
    flow = await agent_flow_service.get_flow(db, flow_id, owner_id)
    if flow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工作流不存在")
    return flow


async def _get_or_create_conversation(db: AsyncSession, flow_id, owner_id) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.flow_id == flow_id, Conversation.owner_id == owner_id
        ).order_by(Conversation.created_at.desc()).limit(1)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        conv = Conversation(flow_id=flow_id, owner_id=owner_id, title="Agent 对话")
        db.add(conv)
        await db.commit()
        await db.refresh(conv)
    return conv


async def _get_owned_conversation(
    db: AsyncSession, flow_id: uuid.UUID, conversation_id: uuid.UUID, owner_id: uuid.UUID
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.flow_id == flow_id,
            Conversation.owner_id == owner_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conv


def _format_history(messages: list[Message]) -> str:
    if not messages:
        return ""
    lines = []
    for m in messages[-10:]:  # 最近 10 轮
        role = "用户" if m.role == MessageRole.user else "助手"
        lines.append(f"{role}: {m.content}")
    return "\n".join(lines)


def _first_start_input_name(dag: dict | None) -> str | None:
    """从 dag 中找开始节点的第一个命名输入变量名。"""
    if not dag:
        return None
    for n in dag.get("nodes", []):
        if n.get("type") == "start":
            inputs = (n.get("data", {}) or {}).get("config", {}).get("inputs")
            if isinstance(inputs, list):
                for inp in inputs:
                    if isinstance(inp, dict) and inp.get("name"):
                        return inp["name"]
    return None


async def _run_and_save_assistant(exec_id: uuid.UUID, conv_id: uuid.UUID, flow_id: uuid.UUID):
    """后台: 运行工作流, 完成后把最终回答作为助手消息存入会话。"""
    try:
        await execution_service.run_flow(exec_id, flow_id)
    except Exception:
        logger.exception("对话后台执行异常: execution=%s flow=%s", exec_id, flow_id)
    async with async_session_factory() as db:
        conv_result = await db.execute(select(Conversation.id).where(Conversation.id == conv_id))
        if conv_result.scalar_one_or_none() is None:
            logger.info("会话已删除，跳过保存助手消息: conversation=%s", conv_id)
            return
        res = await db.execute(select(Execution).where(Execution.id == exec_id))
        ex = res.scalar_one_or_none()
        answer = _final_answer(ex) if ex else "(执行失败)"
        db.add(Message(conversation_id=conv_id, role=MessageRole.assistant, content=answer))
        await db.commit()


@router.get("/{flow_id}/chat/conversations", response_model=list[ConversationRead])
async def list_conversations(flow_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """列出当前用户在该工作流下的全部会话，新 Agent 自动获得一个空会话。"""
    await _get_owned_flow(db, flow_id, current_user.id)
    await _get_or_create_conversation(db, flow_id, current_user.id)
    result = await db.execute(
        select(Conversation).where(
            Conversation.flow_id == flow_id, Conversation.owner_id == current_user.id
        ).order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
    )
    return [ConversationRead.model_validate(conv) for conv in result.scalars().all()]


@router.post(
    "/{flow_id}/chat/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(flow_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """为一个 Agent 新建独立会话。"""
    await _get_owned_flow(db, flow_id, current_user.id)
    conv = Conversation(flow_id=flow_id, owner_id=current_user.id, title="新对话")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationRead.model_validate(conv)


@router.delete(
    "/{flow_id}/chat/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    flow_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """删除一个会话及其消息，所有权同时受工作流和会话约束。"""
    await _get_owned_flow(db, flow_id, current_user.id)
    conv = await _get_owned_conversation(db, flow_id, conversation_id, current_user.id)
    await db.delete(conv)
    await db.commit()


@router.get("/{flow_id}/chat/messages", response_model=list[MessageRead])
async def list_messages(
    flow_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
    conversation_id: uuid.UUID | None = None,
):
    """获取指定会话的消息历史；未指定时兼容旧客户端并使用最新会话。"""
    await _get_owned_flow(db, flow_id, current_user.id)
    conv = (
        await _get_owned_conversation(db, flow_id, conversation_id, current_user.id)
        if conversation_id
        else await _get_or_create_conversation(db, flow_id, current_user.id)
    )
    result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    return [MessageRead.model_validate(m) for m in result.scalars().all()]


@router.post("/{flow_id}/chat", response_model=ChatResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat(flow_id: uuid.UUID, data: ChatRequest, current_user: CurrentUser, db: DBSession):
    """触发一轮对话: 保存用户消息, 异步运行工作流, 立即返回 execution_id。

    前端拿到 execution_id 后轮询 GET .../chat/messages, 出现新的助手消息即为回答。
    """
    flow = await _get_owned_flow(db, flow_id, current_user.id)
    conv = (
        await _get_owned_conversation(db, flow_id, data.conversation_id, current_user.id)
        if data.conversation_id
        else await _get_or_create_conversation(db, flow_id, current_user.id)
    )

    # 读取历史
    msgs_result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    prior = msgs_result.scalars().all()
    history = _format_history(prior)

    # 存用户消息
    if not prior and conv.title in {"新对话", "Agent 对话"}:
        conv.title = data.message.strip().replace("\n", " ")[:50] or "新对话"
    db.add(Message(conversation_id=conv.id, role=MessageRole.user, content=data.message))
    await db.commit()

    # 构造执行输入: 消息作为 {input}/{sys.query}; 同时填入开始节点首个命名输入
    exec_input = {"input": data.message, "sys.query": data.message, "history": history}
    start_named = _first_start_input_name(flow.dag)
    if start_named:
        exec_input[start_named] = data.message

    execution = await agent_flow_service.create_execution(db, flow_id, exec_input)

    # 后台运行 + 存助手消息 (持引用防 GC, 完成后自动移除)
    task = asyncio.create_task(_run_and_save_assistant(execution.id, conv.id, flow_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return ChatResponse(execution_id=execution.id, conversation_id=conv.id, status=execution.status)
