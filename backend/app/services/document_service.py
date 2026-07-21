"""文档处理业务逻辑: 上传 → DeepDoc 解析 → 分块 → 向量化 → ES 索引 → 检索。

对齐 PRD 第 3.1 节完整管线。异步解析通过 FastAPI BackgroundTasks 触发。
"""

import asyncio
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.es_client import delete_doc_chunks, hybrid_search as es_hybrid_search, index_chunks_bulk
from app.core.minio_client import delete_file, download_file, upload_file
from app.core.tei_client import embed_query, embed_texts
from app.models.chunk import Chunk, ContentType
from app.models.document import Document, ParseStatus
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import SearchRequest, SearchResponse, SearchHit
from app.services import deepdoc_service, kb_service

logger = logging.getLogger("claw.doc_service")


# ── 上传 ──

async def upload_document(
    db: AsyncSession, kb: KnowledgeBase, filename: str, file_data: bytes, content_type: str
) -> Document:
    """上传文档到 MinIO，创建 Document 记录 (status=pending)。"""
    doc_id = uuid.uuid4()
    object_name = f"{kb.id}/{doc_id}/{filename}"

    # 存储到 MinIO (同步 SDK 调用放入线程池, 避免阻塞事件循环)
    await asyncio.to_thread(upload_file, object_name, file_data, content_type)

    # 创建 DB 记录
    doc = Document(
        id=doc_id,
        kb_id=kb.id,
        filename=filename,
        file_path=object_name,
        file_size=len(file_data),
        parse_status=ParseStatus.pending,
    )
    db.add(doc)

    # 更新知识库文档计数
    await kb_service.increment_doc_count(db, kb.id, delta=1)
    await db.commit()
    await db.refresh(doc)

    logger.info("文档上传: %s → %s (%d bytes)", filename, doc.id, len(file_data))
    return doc


# ── 异步解析+索引管线 ──

async def parse_and_index(doc_id: uuid.UUID, kb_id: uuid.UUID) -> None:
    """后台任务: 解析文档 → 分块 → 向量化 → ES 索引。

    使用独立的 DB session (不在请求上下文内)。
    """
    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        # 加载文档
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc is None:
            logger.error("文档不存在: %s", doc_id)
            return

        # 加载知识库 (获取分块参数)
        kb_result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
        kb = kb_result.scalar_one_or_none()
        if kb is None:
            logger.error("知识库不存在: %s", kb_id)
            return

        try:
            # ── 1. 标记为 parsing ──
            doc.parse_status = ParseStatus.parsing
            await db.commit()

            # ── 2. 从 MinIO 下载 (同步 SDK 调用放入线程池) ──
            file_data = await asyncio.to_thread(download_file, doc.file_path)

            # ── 3. DeepDoc 解析 (CPU 密集 + 同步, 放入线程池) ──
            blocks = await asyncio.to_thread(
                deepdoc_service.parse_document,
                doc.filename, file_data, chunk_token_num=kb.chunk_size,
            )
            doc.page_count = len({b["page"] for b in blocks}) if blocks else 0
            doc.parse_result = {
                "block_count": len(blocks),
                "content_types": list({b["content_type"] for b in blocks}),
            }

            if not blocks:
                logger.warning("文档解析结果为空: %s", doc.filename)
                doc.parse_status = ParseStatus.parsed
                await db.commit()
                return

            # ── 4. 分块 (基于 DeepDoc 已有的块 + 知识库 chunk_strategy) ──
            chunks_data = await asyncio.to_thread(_create_chunks, blocks, kb)

            # ── 5. TEI 批量向量化 ──
            texts = [c["content"] for c in chunks_data]
            logger.info("开始向量化 %d chunks (doc=%s)", len(texts), doc_id)
            embeddings = await embed_texts(texts)
            if len(embeddings) != len(chunks_data):
                raise RuntimeError(
                    f"向量化数量不符: 期望 {len(chunks_data)}, 实际 {len(embeddings)}"
                )

            # ── 6. 写入 DB chunk 记录 ──
            chunk_records = []
            es_docs = []
            for i, chunk_data in enumerate(chunks_data):
                chunk = Chunk(
                    doc_id=doc.id,
                    kb_id=kb.id,
                    content=chunk_data["content"],
                    content_type=ContentType(chunk_data["content_type"]),
                    page=chunk_data["page"],
                    embedding_stored=True,
                    chunk_metadata=chunk_data.get("metadata"),
                )
                db.add(chunk)
                chunk_records.append(chunk)

                es_docs.append({
                    "chunk_id": str(chunk.id),  # 使用 DB 生成的 UUID
                    "kb_id": str(kb.id),
                    "doc_id": str(doc.id),
                    "content": chunk_data["content"],
                    "content_type": chunk_data["content_type"],
                    "page": chunk_data["page"],
                    "embedding": embeddings[i] if i < len(embeddings) else [],
                    "metadata": chunk_data.get("metadata", {}),
                })

            await db.flush()  # 获取 chunk.id

            # 更新 es_docs 中的 chunk_id (flush 后 id 已生成)
            for i, chunk in enumerate(chunk_records):
                es_docs[i]["chunk_id"] = str(chunk.id)

            # ── 7. ES 批量索引 ──
            indexed = await index_chunks_bulk(es_docs)
            if indexed != len(es_docs):
                raise RuntimeError(f"ES 索引数量不符: 期望 {len(es_docs)}, 实际 {indexed}")
            logger.info("ES 索引完成: %d/%d chunks (doc=%s)", indexed, len(es_docs), doc_id)

            # ── 8. 标记完成 ──
            doc.parse_status = ParseStatus.parsed
            await db.commit()

            logger.info("文档解析+索引完成: %s (%d chunks)", doc.filename, len(chunks_data))

        except Exception as e:
            logger.exception("文档解析失败: %s — %s", doc.filename, e)
            doc.parse_status = ParseStatus.failed
            # 失败原因写入 parse_result, 供前端/排查查看
            doc.parse_result = {"error": f"{type(e).__name__}: {e}"[:1000]}
            await db.commit()


def _create_chunks(blocks: list[dict], kb: KnowledgeBase) -> list[dict]:
    """将 DeepDoc 解析的 blocks 按 chunk_strategy 分块。

    DeepDoc 已做了初步分块 (基于 token 数和分隔符)。
    这里根据知识库的 chunk_strategy 做进一步处理:
      - recursive: 保留 DeepDoc 分块, 大块再切分
      - fixed: 固定长度切分
      - markdown: 保留 DeepDoc 分块 (MarkdownParser 已处理)
      - semantic: M2 降级为 recursive (语义分块留 M2.5)

    Token 计数/截断使用 common.token_utils (tiktoken), 与 DeepDoc 一致。
    """
    from common.token_utils import num_tokens_from_string

    chunks = []
    chunk_size = kb.chunk_size
    chunk_overlap = kb.chunk_overlap

    for block in blocks:
        content = block["content"]
        content_type = block["content_type"]
        page = block["page"]

        if not content.strip():
            continue

        # 表格类不切分, 整块保留
        if content_type == "table":
            chunks.append({
                "content": content,
                "content_type": "table",
                "page": page,
                "metadata": {"source": "deepdoc_table"},
            })
            continue

        # 文本类: 按 chunk_strategy 处理
        token_count = num_tokens_from_string(content)

        if kb.chunk_strategy.value == "fixed":
            # 固定长度切分 (按 token)
            _split_and_append(content, content_type, page, chunk_size, chunk_overlap,
                              token_count, "fixed", chunks)
        else:
            # recursive / markdown / semantic → 保留 DeepDoc 分块
            # 如果块太大 (超过 chunk_size*2), 按 token 截断切分
            if token_count > chunk_size * 2:
                _split_and_append(content, content_type, page, chunk_size, chunk_overlap,
                                  token_count, "recursive_split", chunks)
            else:
                chunks.append({
                    "content": content,
                    "content_type": "text",
                    "page": page,
                    "metadata": {"source": "deepdoc", "token_count": token_count},
                })

    return chunks


def _split_and_append(
    content: str, content_type: str, page: int,
    chunk_size: int, chunk_overlap: int, token_count: int,
    source: str, chunks: list
) -> None:
    """按 token 窗口切分文本块, 追加到 chunks 列表 (基于 slice_tokens 精确切片)。"""
    from common.token_utils import slice_tokens

    pos = 0
    step = max(1, chunk_size - chunk_overlap)
    while pos < token_count:
        end = min(pos + chunk_size, token_count)
        chunk_text = slice_tokens(content, pos, end)

        if chunk_text.strip():
            chunks.append({
                "content": chunk_text,
                "content_type": content_type,
                "page": page,
                "metadata": {"source": source, "token_start": pos, "token_end": end},
            })
        pos += step
        if pos >= end:
            break


# ── 文档管理 ──

async def list_documents(db: AsyncSession, kb_id) -> list[Document]:
    """列出知识库下的文档。"""
    result = await db.execute(
        select(Document).where(Document.kb_id == kb_id).order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document(db: AsyncSession, doc_id) -> Document | None:
    """获取文档。"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()


async def delete_document(db: AsyncSession, doc: Document) -> None:
    """删除文档及其 chunk 和 ES 索引。"""
    doc_id_str = str(doc.id)

    # 1. 删除 ES 中的 chunk 索引
    try:
        await delete_doc_chunks(doc_id_str)
    except Exception as e:
        logger.warning("删除 ES chunk 索引失败 (doc=%s): %s", doc_id_str, e)

    # 2. 删除 MinIO 文件
    try:
        await asyncio.to_thread(delete_file, doc.file_path)
    except Exception as e:
        logger.warning("删除 MinIO 文件失败 (doc=%s): %s", doc.id, e)

    # 3. 更新知识库计数
    await kb_service.increment_doc_count(db, doc.kb_id, delta=-1)

    # 4. 删除 DB 记录 (cascade 删除 chunks)
    await db.delete(doc)
    await db.commit()
    logger.info("文档删除: %s", doc_id_str)


async def reset_document_for_reparse(db: AsyncSession, doc: Document) -> None:
    """重解析前置: 清除旧 chunk (DB + ES), 重置解析状态为 pending。"""
    doc_id_str = str(doc.id)

    # 1. 删除 ES 中的旧 chunk 索引
    try:
        await delete_doc_chunks(doc_id_str)
    except Exception as e:
        logger.warning("删除 ES chunk 索引失败 (doc=%s): %s", doc_id_str, e)

    # 2. 删除 DB 中的旧 chunk
    await db.execute(delete(Chunk).where(Chunk.doc_id == doc.id))

    # 3. 重置解析状态
    doc.parse_status = ParseStatus.pending
    doc.page_count = 0
    doc.parse_result = None
    await db.commit()
    await db.refresh(doc)  # 刷新 onupdate 服务端列 (updated_at), 供响应序列化
    logger.info("文档重置待重解析: %s", doc_id_str)


# ── Chunk 查询 ──

async def list_chunks(db: AsyncSession, kb_id, doc_id=None, page: int = 1, page_size: int = 20) -> tuple[list[Chunk], int]:
    """列出 chunk。"""
    base_query = select(Chunk).where(Chunk.kb_id == kb_id)
    if doc_id:
        base_query = base_query.where(Chunk.doc_id == doc_id)

    from sqlalchemy import func
    total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(
        base_query.order_by(Chunk.created_at).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


# ── 检索 ──

async def search(db: AsyncSession, kb_id, request: SearchRequest) -> SearchResponse:
    """混合检索: TEI 向量化 query → ES kNN + BM25 + (可选) Cross-Encoder 重排序。

    底层依赖 (embedding/ES) 异常统一转为 503, 不向调用方泄漏内部错误细节。
    """
    kb_id_str = str(kb_id)

    try:
        # 1. 向量化查询
        query_vector = await embed_query(request.query)

        # 2. ES 混合检索 — 如果启用重排序, over-fetch 候选 (4x) 供 reranker 精排
        fetch_k = request.top_k * 4 if request.rerank else request.top_k
        hits = await es_hybrid_search(
            kb_id=kb_id_str,
            query_vector=query_vector,
            query_text=request.query,
            top_k=fetch_k,
        )

        # 3. Cross-Encoder 重排序 (M4)
        if request.rerank and hits:
            try:
                from app.core.reranker_client import rerank as rerank_docs
                documents = [h["content"] for h in hits]
                rerank_top_k = request.rerank_top_k or request.top_k
                ranked = await rerank_docs(request.query, documents, top_k=rerank_top_k)
                # 按 reranker 的 index 重新排列 hits, 写入 rerank_score
                reranked_hits = []
                for item in ranked:
                    idx = item["index"]
                    if 0 <= idx < len(hits):
                        h = dict(hits[idx])
                        h["rerank_score"] = item["score"]
                        reranked_hits.append(h)
                hits = reranked_hits
                logger.info("重排序生效: %d → %d hits", len(documents), len(hits))
            except Exception as e:
                logger.warning("重排序失败, 使用原始检索结果: %s", e)

        # 4. 过滤阈值
        if request.threshold > 0:
            hits = [h for h in hits if h["score"] >= request.threshold]

        search_hits = [SearchHit(**h) for h in hits]
        logger.info("检索完成 kb=%s query='%s' rerank=%s → %d hits", kb_id_str, request.query[:50], request.rerank, len(search_hits))

        return SearchResponse(
            query=request.query,
            total=len(search_hits),
            hits=search_hits,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("检索失败 kb=%s: %s", kb_id_str, e)
        raise HTTPException(
            status_code=503, detail="检索服务暂不可用，请稍后重试"
        ) from e
