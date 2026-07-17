"""记忆系统端点。对齐 PRD 5.1。"""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DBSession
from app.models.memory import Memory, MemoryType
from app.schemas.memory import (
    MemoryCreate,
    MemoryRead,
    MemoryUpdate,
)
from app.services import memory_service

router = APIRouter(prefix="/memories", tags=["记忆系统"])


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(data: MemoryCreate, current_user: CurrentUser, db: DBSession):
    """创建记忆。"""
    memory = await memory_service.save_memory(
        db, current_user.id, data.type, data.key, data.value, data.session_id
    )
    return MemoryRead.model_validate(memory)


@router.get("", response_model=list[MemoryRead])
async def list_memories(
    current_user: CurrentUser,
    db: DBSession,
    type: MemoryType | None = Query(None),
    session_id: str | None = Query(None),
):
    """列出当前用户的记忆 (可按 type/session 过滤)。"""
    memories = await memory_service.list_memories(db, current_user.id, type, session_id)
    return [MemoryRead.model_validate(m) for m in memories]


@router.get("/search", response_model=list[MemoryRead])
async def search_memories(
    current_user: CurrentUser,
    db: DBSession,
    q: str = Query(..., min_length=1, description="搜索关键词"),
    top_k: int = Query(5, ge=1, le=50),
    session_id: str | None = Query(None),
):
    """关键词搜索记忆 (GET, 查询参数 q)。"""
    memories = await memory_service.search_memories(
        db, current_user.id, q, top_k, session_id
    )
    return [MemoryRead.model_validate(m) for m in memories]


@router.get("/{memory_id}", response_model=MemoryRead)
async def get_memory(memory_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """获取记忆详情。"""
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None or memory.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记忆不存在")
    return MemoryRead.model_validate(memory)


@router.put("/{memory_id}", response_model=MemoryRead)
async def update_memory(memory_id: uuid.UUID, data: MemoryUpdate, current_user: CurrentUser, db: DBSession):
    """更新记忆。"""
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None or memory.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记忆不存在")

    if data.value is not None:
        memory.value = data.value
    await db.commit()
    await db.refresh(memory)
    return MemoryRead.model_validate(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """删除记忆。"""
    result = await db.execute(select(Memory).where(Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None or memory.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记忆不存在")
    await memory_service.delete_memory(db, memory)
