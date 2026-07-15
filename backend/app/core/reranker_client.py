"""Cross-Encoder 重排序客户端。

通过 TEI (Text Embeddings Inference) sidecar 加载 BAAI/bge-reranker-v2-m3,
调用 /rerank HTTP API 对检索结果进行二次排序, 提升相关性精度。

TEI Rerank API:
  POST /rerank — body: {"query": "...", "texts": ["doc1", ...], "return_text": false}
  返回: [{"index": 0, "score": 0.95}, ...]  (按 score 降序)
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("claw.reranker")


async def rerank(
    query: str,
    documents: list[str],
    top_k: int = 5,
    timeout: float = 30.0,
) -> list[dict]:
    """对文档列表进行 Cross-Encoder 重排序。

    Args:
        query: 查询文本
        documents: 待排序的文档内容列表
        top_k: 返回前 K 条
        timeout: HTTP 超时

    Returns:
        重排序后的结果列表, 每项含 {index, score} (按 score 降序)
        index 指向原始 documents 列表的位置。
    """
    if not documents:
        return []

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.reranker_url}/rerank",
            json={
                "query": query,
                "texts": documents,
                "return_text": False,
            },
        )
        resp.raise_for_status()
        results = resp.json()

    # TEI 返回格式: [{"index": 0, "score": 0.95}, ...]
    # 已按 score 降序排列
    ranked = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    if top_k > 0:
        ranked = ranked[:top_k]

    logger.info("重排序完成: query='%s' → %d docs → top %d", query[:50], len(documents), len(ranked))
    return ranked


async def health_check() -> bool:
    """Reranker 连通性检查。"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.reranker_url}/health")
            return resp.status_code < 500
    except Exception:
        return False
