"""知识库 CRUD 业务逻辑。对齐 PRD 5.1 / 6.1。"""

import asyncio
import logging

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.es_client import delete_kb_chunks
from app.core.minio_client import delete_file
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KBCreate, KBUpdate

logger = logging.getLogger("claw.kb_service")


async def create_kb(db: AsyncSession, owner_id, data: KBCreate) -> KnowledgeBase:
    """创建知识库。"""
    kb = KnowledgeBase(
        name=data.name,
        description=data.description,
        owner_id=owner_id,
        embedding_model=data.embedding_model,
        chunk_strategy=data.chunk_strategy,
        chunk_size=data.chunk_size,
        chunk_overlap=data.chunk_overlap,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    logger.info("知识库创建: %s (%s)", kb.name, kb.id)
    return kb


async def list_kbs(db: AsyncSession, owner_id, page: int = 1, page_size: int = 20) -> tuple[list[KnowledgeBase], int]:
    """列出用户的知识库 (owner 隔离)。"""
    base_query = select(KnowledgeBase).where(KnowledgeBase.owner_id == owner_id)
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(
        base_query.order_by(KnowledgeBase.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(result.scalars().all())
    return items, total


async def get_kb(db: AsyncSession, kb_id, owner_id) -> KnowledgeBase | None:
    """获取知识库 (owner 隔离)。"""
    result = await db.execute(
        select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def get_kb_no_owner_check(db: AsyncSession, kb_id) -> KnowledgeBase | None:
    """获取知识库 (不检查 owner, 内部使用)。"""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    return result.scalar_one_or_none()


async def update_kb(db: AsyncSession, kb: KnowledgeBase, data: KBUpdate) -> KnowledgeBase:
    """更新知识库元数据。"""
    if data.name is not None:
        kb.name = data.name
    if data.description is not None:
        kb.description = data.description
    await db.commit()
    await db.refresh(kb)
    return kb


async def delete_kb(db: AsyncSession, kb: KnowledgeBase) -> None:
    """删除知识库及其所有文档、chunk、ES 索引、MinIO 文件。"""
    kb_id_str = str(kb.id)

    # 1. 删除 ES 中的 chunk 索引
    try:
        await delete_kb_chunks(kb_id_str)
    except Exception as e:
        logger.warning("删除 ES chunk 索引失败 (kb=%s): %s", kb_id_str, e)

    # 2. 删除 MinIO 中的文件
    docs_result = await db.execute(select(Document).where(Document.kb_id == kb.id))
    for doc in docs_result.scalars().all():
        try:
            await asyncio.to_thread(delete_file, doc.file_path)
        except Exception as e:
            logger.warning("删除 MinIO 文件失败 (doc=%s): %s", doc.id, e)

    # 3. 删除 DB 记录 (cascade 会自动删除 documents + chunks)
    await db.delete(kb)
    await db.commit()
    logger.info("知识库删除: %s", kb_id_str)


async def increment_doc_count(db: AsyncSession, kb_id, delta: int = 1) -> None:
    """更新知识库文档计数。"""
    kb = await get_kb_no_owner_check(db, kb_id)
    if kb:
        kb.document_count = max(0, kb.document_count + delta)
        await db.commit()
