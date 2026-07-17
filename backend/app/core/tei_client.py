"""TEI (Text Embeddings Inference) 客户端。

对齐 PRD 第 3.1 节: BGE-M3 模型通过 TEI sidecar 提供 1024 维向量。
TEI HTTP API:
  POST /embed  — body: {"inputs": "text" | ["text1", "text2", ...]}
  返回: [[0.1, 0.2, ...], ...]  (每个输入一个 1024 维向量)
"""

import hashlib
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("claw.tei")


def _mock_vector(text: str) -> list[float]:
    """确定性哈希向量 (dev 兜底): TEI 不可达时, 用文本哈希生成稳定向量。

    相同文本 → 相同向量, 保证检索可复现。语义性弱, 仅用于离线演示;
    BM25 全文检索仍提供真实文本匹配。
    """
    dim = settings.embedding_dim
    vec = [0.0] * dim
    # 用多轮哈希填充各维, 使不同文本向量差异明显
    for i in range(dim):
        h = hashlib.sha256(f"{text}:{i}".encode("utf-8")).digest()
        vec[i] = (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) - 0.5
    # 归一化为单位向量 (kNN cosine 友好)
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


async def embed_texts(texts: list[str], timeout: float = 60.0) -> list[list[float]]:
    """批量文本向量化。返回与输入等长的向量列表 (每个 embedding_dim 维)。

    优先级: Embedding API (OpenAI 兼容 /v1/embeddings) → TEI sidecar → dev 哈希兜底。
    """
    if not texts:
        return []

    cleaned = [t.strip() if t else " " for t in texts]

    # 1. 优先: Embedding 模型 API (管理员在模型配置界面配置)
    from app.core import embedding_config
    cfg = embedding_config.get()
    if cfg["base_url"] and cfg["api_key"]:
        try:
            return await _embed_via_api(cleaned, cfg["base_url"], cfg["api_key"], cfg["model"], timeout)
        except Exception as e:
            logger.warning("Embedding API 调用失败, 回落 TEI: %s", e)

    # 2. TEI sidecar (分批避免 413)
    BATCH = 16
    out: list[list[float]] = []
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for i in range(0, len(cleaned), BATCH):
                batch = cleaned[i:i + BATCH]
                resp = await client.post(
                    f"{settings.tei_url}/embed",
                    json={"inputs": batch},
                )
                resp.raise_for_status()
                out.extend(resp.json())
        logger.info("TEI 向量化: %d texts → %d dims", len(cleaned), len(out[0]) if out else 0)
        return out
    except Exception as e:
        if settings.environment == "dev":
            logger.warning("TEI 不可达, dev 回退哈希向量: %s", e)
            return [_mock_vector(t) for t in cleaned]
        raise


async def _embed_via_api(
    texts: list[str], base_url: str, api_key: str, model: str, timeout: float
) -> list[list[float]]:
    """调用 OpenAI 兼容的 /v1/embeddings 端点。"""
    payload_model = model or settings.embedding_model
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": payload_model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
    # OpenAI 格式: {data: [{embedding: [...]}, ...]} (按 index 排序)
    items = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
    vectors = [it["embedding"] for it in items]
    logger.info("Embedding API 向量化: %d texts → %d dims", len(vectors), len(vectors[0]) if vectors else 0)
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
