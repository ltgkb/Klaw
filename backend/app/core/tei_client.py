"""TEI (Text Embeddings Inference) 客户端。

对齐 PRD 第 3.1 节: BGE-M3 模型通过 TEI sidecar 提供 1024 维向量。
TEI HTTP API:
  POST /embed  — body: {"inputs": "text" | ["text1", "text2", ...]}
  返回: [[0.1, 0.2, ...], ...]  (每个输入一个 1024 维向量)
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("claw.tei")


async def embed_texts(texts: list[str], timeout: float = 60.0) -> list[list[float]]:
    """批量文本向量化。返回与输入等长的向量列表 (每个 1024 维)。

    Args:
        texts: 待向量化的文本列表
        timeout: HTTP 超时 (秒), 批量大时需增加

    Returns:
        list[list[float]] — 每个元素是 embedding_dim 维浮点向量
    """
    if not texts:
        return []

    # 清理文本: 去除首尾空白, 跳过空串
    cleaned = [t.strip() if t else " " for t in texts]

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.tei_url}/embed",
            json={"inputs": cleaned},
        )
        resp.raise_for_status()
        vectors = resp.json()

    logger.info("TEI 向量化: %d texts → %d dims", len(cleaned), len(vectors[0]) if vectors else 0)
    return vectors


async def embed_query(text: str, timeout: float = 10.0) -> list[float]:
    """单条查询向量化 (检索时使用)。"""
    vectors = await embed_texts([text], timeout=timeout)
    return vectors[0] if vectors else []


async def health_check() -> bool:
    """TEI 连通性检查。"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.tei_url}/health")
            return resp.status_code < 500
    except Exception:
        return False
