"""记忆系统业务逻辑。对齐 PRD 5.1。

短期记忆存 Redis，长期/工作区记忆存 PostgreSQL (Memory 表)。
本模块实现 PostgreSQL 持久记忆的 CRUD + 关键词搜索。
"""

import logging

from sqlalchemy import Text, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory, MemoryType

logger = logging.getLogger("claw.memory")


async def save_memory(
    db: AsyncSession,
    user_id,
    type: MemoryType,
    key: str,
    value: dict,
    session_id: str | None = None,
) -> Memory:
    """保存记忆。如果同 user+key+session 已存在则更新。"""
    # 查找已有记忆 (同 user + key + session_id)
    query = select(Memory).where(Memory.user_id == user_id, Memory.key == key)
    if session_id:
        query = query.where(Memory.session_id == session_id)
    else:
        query = query.where(Memory.session_id.is_(None))
    result = await db.execute(query)
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = value
        existing.type = type
        await db.commit()
        await db.refresh(existing)
        logger.info("记忆更新: key=%s user=%s", key, user_id)
        return existing

    memory = Memory(
        user_id=user_id,
        type=type,
        key=key,
        value=value,
        session_id=session_id,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    logger.info("记忆创建: key=%s user=%s", key, user_id)
    return memory


async def get_memory(
    db: AsyncSession,
    user_id,
    key: str,
    session_id: str | None = None,
) -> Memory | None:
    """获取单条记忆。"""
    query = select(Memory).where(Memory.user_id == user_id, Memory.key == key)
    if session_id:
        query = query.where(Memory.session_id == session_id)
    else:
        query = query.where(Memory.session_id.is_(None))
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_memories(
    db: AsyncSession,
    user_id,
    type: MemoryType | None = None,
    session_id: str | None = None,
) -> list[Memory]:
    """列出用户记忆 (可按 type/session 过滤)。"""
    query = select(Memory).where(Memory.user_id == user_id)
    if type:
        query = query.where(Memory.type == type)
    if session_id:
        query = query.where(Memory.session_id == session_id)
    query = query.order_by(Memory.updated_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_memory(db: AsyncSession, memory: Memory) -> None:
    """删除记忆。"""
    await db.delete(memory)
    await db.commit()
    logger.info("记忆删除: %s", memory.id)


async def search_memories(
    db: AsyncSession,
    user_id,
    query: str,
    top_k: int = 5,
    session_id: str | None = None,
) -> list[Memory]:
    """关键词搜索记忆 (在 key 和 value 的文本中匹配)。"""
    # PostgreSQL JSON 文本搜索 (简化: 在 key 和 value::text 中 ilike)
    pattern = f"%{query}%"
    stmt = select(Memory).where(
        Memory.user_id == user_id,
        or_(
            Memory.key.ilike(pattern),
            Memory.value.cast(Text).ilike(pattern),
        ),
    )
    if session_id:
        stmt = stmt.where(Memory.session_id == session_id)
    stmt = stmt.order_by(Memory.updated_at.desc()).limit(top_k)
    result = await db.execute(stmt)
    return list(result.scalars().all())
