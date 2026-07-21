"""Elasticsearch 异步客户端 + 知识库索引管理。

对齐 PRD 第 5.2 节: dense_vector (kNN) + BM25 (IK 分词) 混合检索。
ES 8.11 原生支持 dense_vector + knn，IK 插件提供中文分词。
"""

import asyncio
import json
import logging

from elasticsearch import AsyncElasticsearch, NotFoundError

from app.core.config import settings

logger = logging.getLogger("claw.es")

# bulk 分批与重试参数: 8GB 生产机上 ES 堆 1g, 单个 bulk 请求需远小于
# coordinating_operation_bytes 上限 (默认 heap 10%), 否则触发 429。
_BULK_MAX_CHUNKS = 100                  # 每批最多 chunk 条数
_BULK_MAX_BYTES = 5 * 1024 * 1024       # 每批估算字节上限 5MB
_BULK_RETRY_DELAYS = (2.0, 5.0, 10.0)   # 429 类可恢复错误指数退避 (秒), 共 3 次重试

_client: AsyncElasticsearch | None = None


def get_es_client() -> AsyncElasticsearch:
    """获取 ES 异步单例。"""
    global _client
    if _client is None:
        _client = AsyncElasticsearch(settings.es_url)
    return _client


async def close_es_client() -> None:
    """关闭 ES 连接 (应用退出时调用)。"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ensure_kb_index() -> None:
    """确保知识库 chunk 索引存在，不存在则按 M2 设计创建。

    索引结构 (PRD 第 5.2 节):
      - embedding: dense_vector, 1024 维, dot_product 相似度
      - content: text, ik_max_word 分词 (索引) / ik_smart (搜索)
      - content_type / doc_id / kb_id / chunk_id: keyword
      - page: integer
      - metadata: object (不索引, 仅存储)
    """
    es = get_es_client()
    index_name = settings.es_kb_index

    exists = await es.indices.exists(index=index_name)
    if exists:
        logger.info("ES 索引已存在: %s", index_name)
        return

    mapping = {
        "mappings": {
            "properties": {
                "embedding": {
                    "type": "dense_vector",
                    "dims": settings.embedding_dim,
                    "index": True,
                    "similarity": "dot_product",
                },
                "content": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                },
                "content_type": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "kb_id": {"type": "keyword"},
                "chunk_id": {"type": "keyword"},
                "page": {"type": "integer"},
                "metadata": {"type": "object", "enabled": False},
            }
        }
    }

    await es.indices.create(index=index_name, body=mapping)
    logger.info("ES 索引创建成功: %s (dims=%d)", index_name, settings.embedding_dim)


async def index_chunks_bulk(chunks: list[dict]) -> int:
    """批量索引 chunk 到 ES。

    每个 chunk dict 需包含: chunk_id, kb_id, doc_id, content, content_type, page, embedding, metadata。
    开头确保索引存在; bulk 响应中任何条目出错即解析错误并 raise。
    返回成功索引的文档数。

    生产机 ES 堆较小 (1g), 整篇文档一次性 bulk 会触发
    coordinating_operation_bytes / circuit_breaking 429, 因此:
      - 按「条数 ≤ _BULK_MAX_CHUNKS 且估算字节 ≤ _BULK_MAX_BYTES」分批发送;
      - 每批遇 429 / circuit_breaking / rejected_execution 类可恢复错误时
        按 _BULK_RETRY_DELAYS 指数退避重试, 耗尽后再 raise;
      - 仅最后一批 refresh=True, 中间批 refresh=False (减少段合并压力)。
    """
    if not chunks:
        return 0

    await ensure_kb_index()

    es = get_es_client()
    index_name = settings.es_kb_index

    # ── 构造每 chunk 的 (action, source) 并按条数+字节分批 ──
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_bytes = 0
    for chunk in chunks:
        action = {"index": {"_index": index_name, "_id": chunk["chunk_id"]}}
        source = {
            "chunk_id": chunk["chunk_id"],
            "kb_id": str(chunk["kb_id"]),
            "doc_id": str(chunk["doc_id"]),
            "content": chunk["content"],
            "content_type": chunk["content_type"],
            "page": chunk.get("page", 0),
            "embedding": chunk["embedding"],
            "metadata": chunk.get("metadata", {}),
        }
        size = len(json.dumps(source, ensure_ascii=False, default=str).encode("utf-8")) + 128
        if current and (len(current) // 2 >= _BULK_MAX_CHUNKS or current_bytes + size > _BULK_MAX_BYTES):
            batches.append(current)
            current, current_bytes = [], 0
        current.extend((action, source))
        current_bytes += size
    if current:
        batches.append(current)

    # ── 分批发送, 仅最后一批 refresh ──
    for i, batch in enumerate(batches):
        refresh = i == len(batches) - 1
        result = await _bulk_with_retry(es, batch, refresh)
        if result.get("errors"):
            errors = [item["index"]["error"] for item in result.get("items", []) if "error" in item.get("index", {})]
            logger.error("ES bulk 索引部分失败: %d/%d — %s", len(errors), len(chunks), errors[:3])
            raise RuntimeError(f"ES bulk 索引失败 {len(errors)}/{len(chunks)}: {errors[0] if errors else 'unknown'}")
        logger.info("ES bulk 批次 %d/%d 索引成功: %d chunks", i + 1, len(batches), len(batch) // 2)

    logger.info("ES bulk 索引成功: %d chunks (%d 批)", len(chunks), len(batches))
    return len(chunks)


def _is_recoverable_bulk_error(exc: Exception) -> bool:
    """判断 bulk 异常是否为 429 / 熔断 / 拒绝执行类可恢复错误。"""
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "meta", None), "status", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "too_many_requests" in text or "circuit_breaking" in text or "rejected_execution" in text


async def _bulk_with_retry(es: AsyncElasticsearch, operations: list[dict], refresh: bool):
    """发送单批 bulk, 可恢复错误按指数退避重试, 耗尽后原样 raise。"""
    for attempt in range(len(_BULK_RETRY_DELAYS) + 1):
        try:
            return await es.bulk(operations=operations, refresh=refresh)
        except Exception as exc:
            if attempt >= len(_BULK_RETRY_DELAYS) or not _is_recoverable_bulk_error(exc):
                raise
            delay = _BULK_RETRY_DELAYS[attempt]
            logger.warning(
                "ES bulk 被限流/熔断 (%s), %.0fs 后第 %d/%d 次重试 (%d ops)",
                exc, delay, attempt + 1, len(_BULK_RETRY_DELAYS), len(operations),
            )
            await asyncio.sleep(delay)


async def hybrid_search(
    kb_id: str,
    query_vector: list[float],
    query_text: str,
    top_k: int = 10,
    num_candidates: int | None = None,
) -> list[dict]:
    """混合检索: kNN 向量 + BM25 全文 (disjunction)。

    ES 8.11 使用 knn + query bool should 组合 (RRF retriever 需 8.14+)。
    num_candidates 默认 max(200, top_k*10), 保证 kNN 召回质量。
    索引缺失 (NotFound) 时自动重建索引并重试一次。
    返回 [{chunk_id, doc_id, content, content_type, page, score, metadata}, ...]
    """
    es = get_es_client()
    index_name = settings.es_kb_index
    if num_candidates is None:
        num_candidates = max(200, top_k * 10)

    body = {
        "size": top_k,
        "query": {
            "bool": {
                "filter": [{"term": {"kb_id": kb_id}}],
                "should": [{"match": {"content": query_text}}],
            }
        },
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": num_candidates,
            "filter": {"term": {"kb_id": kb_id}},
        },
    }

    try:
        result = await es.search(index=index_name, body=body)
    except NotFoundError:
        logger.warning("ES 索引不存在, 重建后重试一次: %s", index_name)
        await ensure_kb_index()
        result = await es.search(index=index_name, body=body)
    hits = result.get("hits", {}).get("hits", [])

    results = []
    for hit in hits:
        source = hit["_source"]
        results.append({
            "chunk_id": source.get("chunk_id"),
            "doc_id": source.get("doc_id"),
            "content": source.get("content", ""),
            "content_type": source.get("content_type", "text"),
            "page": source.get("page", 0),
            "score": hit.get("_score", 0.0),
            "metadata": source.get("metadata", {}),
        })

    logger.info("ES 混合检索 kb=%s query='%s' → %d hits", kb_id, query_text[:50], len(results))
    return results


async def delete_doc_chunks(doc_id: str) -> int:
    """删除某文档的所有 chunk 索引。"""
    es = get_es_client()
    index_name = settings.es_kb_index
    result = await es.delete_by_query(
        index=index_name,
        body={"query": {"term": {"doc_id": doc_id}}},
        refresh=True,
    )
    deleted = result.get("deleted", 0)
    logger.info("ES 删除文档 %s 的 %d chunks", doc_id, deleted)
    return deleted


async def delete_kb_chunks(kb_id: str) -> int:
    """删除某知识库的所有 chunk 索引。"""
    es = get_es_client()
    index_name = settings.es_kb_index
    result = await es.delete_by_query(
        index=index_name,
        body={"query": {"term": {"kb_id": kb_id}}},
        refresh=True,
    )
    deleted = result.get("deleted", 0)
    logger.info("ES 删除知识库 %s 的 %d chunks", kb_id, deleted)
    return deleted
