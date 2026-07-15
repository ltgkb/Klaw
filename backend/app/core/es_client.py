"""Elasticsearch 异步客户端 + 知识库索引管理。

对齐 PRD 第 5.2 节: dense_vector (kNN) + BM25 (IK 分词) 混合检索。
ES 8.11 原生支持 dense_vector + knn，IK 插件提供中文分词。
"""

import logging

from elasticsearch import AsyncElasticsearch

from app.core.config import settings

logger = logging.getLogger("claw.es")

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
    返回成功索引的文档数。
    """
    if not chunks:
        return 0

    es = get_es_client()
    index_name = settings.es_kb_index

    actions = []
    for chunk in chunks:
        actions.append({"index": {"_index": index_name, "_id": chunk["chunk_id"]}})
        actions.append({
            "chunk_id": chunk["chunk_id"],
            "kb_id": str(chunk["kb_id"]),
            "doc_id": str(chunk["doc_id"]),
            "content": chunk["content"],
            "content_type": chunk["content_type"],
            "page": chunk.get("page", 0),
            "embedding": chunk["embedding"],
            "metadata": chunk.get("metadata", {}),
        })

    result = await es.bulk(operations=actions, refresh=True)
    if result.get("errors"):
        errors = [item for item in result.get("items", []) if "error" in item.get("index", {})]
        logger.error("ES bulk 索引部分失败: %d/%d", len(errors), len(chunks))
    else:
        logger.info("ES bulk 索引成功: %d chunks", len(chunks))
    return len(chunks)


async def hybrid_search(
    kb_id: str,
    query_vector: list[float],
    query_text: str,
    top_k: int = 10,
    num_candidates: int = 200,
) -> list[dict]:
    """混合检索: kNN 向量 + BM25 全文 (disjunction)。

    ES 8.11 使用 knn + query bool should 组合 (RRF retriever 需 8.14+)。
    返回 [{chunk_id, doc_id, content, content_type, page, score, metadata}, ...]
    """
    es = get_es_client()
    index_name = settings.es_kb_index

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
