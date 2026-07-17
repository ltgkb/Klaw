"""检索质量评测脚本。

用一个小型中文语义数据集, 量化 Claw 知识库检索的真实质量, 并做消融:
  - BM25-only       : 纯关键词 (ES match)
  - Vector-only     : 仅向量 kNN (当前是哈希伪向量)
  - Hybrid (当前)   : 平台 /search (BM25 + 哈希向量)
  - Real-Vector     : 真实语义向量 (sentence-transformers, 可选)

指标: Hit@5 / MRR / Recall@5, 并按 关键词查询 / 语义查询 拆分。
用法 (远端): cd backend && PYTHONPATH=$PWD uv run python scripts/eval_retrieval.py
"""

import io
import asyncio
import time
import sys

import httpx
from elasticsearch import Elasticsearch

from app.core.config import settings
from app.core.tei_client import embed_query  # 真实查询向量化 (走配置的 embedding API)

# ── 评测数据集 ──
DOCS = [
    "退款政策：商品购买后7天内可申请全额退款，需提供订单号，审核通过后原路退回。",
    "配送时效：标准配送3到5个工作日送达，偏远地区可能延长至7天，物流单号可在订单页查看。",
    "账号注销：用户可在设置中心申请注销账号，注销后个人数据将永久清除且不可恢复。",
    "会员等级：累计消费满1000元升级银卡，满5000元升级金卡，金卡享额外九折优惠。",
    "发票开具：支持电子普通发票自助下载，增值税专用发票需联系客服并提供企业开票信息。",
    "密码找回：忘记密码可通过绑定的手机号或邮箱获取验证码重置，验证码5分钟内有效。",
    "商品保修：电子产品享一年免费保修服务，非人为损坏可免费维修或更换。",
    "积分兑换：每消费1元累计1积分，100积分可兑换5元代金券，积分年底清零。",
    "取消订单：未发货订单可随时取消，已发货订单需在签收后申请退货退款。",
    "隐私保护：我们承诺不会向任何第三方共享您的个人信息，所有数据均加密存储。",
]

# (query, relevant_doc_index, type)  type: kw=关键词重叠, sem=语义改写(低词面重叠)
QUERIES = [
    ("怎么申请退款", 0, "kw"),
    ("如何把钱退回来", 0, "sem"),
    ("几天能送到", 1, "sem"),
    ("标准快递要多久", 1, "sem"),
    ("怎么注销账户", 2, "kw"),
    ("账号怎么彻底删除", 2, "sem"),
    ("怎么升级会员", 3, "kw"),
    ("消费多少能成金卡", 3, "kw"),
    ("怎么开发票", 4, "kw"),
    ("增值税专票怎么开", 4, "sem"),
    ("忘记密码怎么办", 5, "kw"),
    ("登不进去如何重置", 5, "sem"),
    ("保修期多久", 6, "kw"),
    ("电子产品坏了能修吗", 6, "sem"),
    ("积分怎么用", 7, "kw"),
    ("100分能换什么", 7, "sem"),
    ("怎么取消订单", 8, "kw"),
    ("发货了还能退吗", 8, "sem"),
    ("你们会泄露我的信息吗", 9, "sem"),
    ("个人信息安全吗", 9, "sem"),
]

API = "http://localhost:8000/api/v1"
EMAIL, PWD = "admin@example.com", "admin123"


def login() -> str:
    r = httpx.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def create_kb(token: str) -> str:
    r = httpx.post(f"{API}/knowledge-bases", headers=_h(token),
                   json={"name": "检索评测", "description": "eval", "chunk_strategy": "fixed",
                         "chunk_size": 256, "chunk_overlap": 16}, timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def upload_docs(token: str, kb_id: str) -> list[str]:
    doc_ids = []
    for i, text in enumerate(DOCS):
        files = {"file": (f"doc{i}.txt", text.encode("utf-8"), "text/plain")}
        r = httpx.post(f"{API}/knowledge-bases/{kb_id}/documents", headers=_h(token), files=files, timeout=60)
        r.raise_for_status()
        doc_ids.append(r.json()["id"])
    # 轮询直到全部解析完
    print(f"  上传 {len(DOCS)} 文档, 等待解析索引...", flush=True)
    for _ in range(60):
        r = httpx.get(f"{API}/knowledge-bases/{kb_id}/documents", headers=_h(token), timeout=30)
        docs = r.json()
        if all(d["parse_status"] == "parsed" for d in docs) and len(docs) == len(DOCS):
            break
        time.sleep(2)
    else:
        print("  警告: 部分文档未在时限内解析完", flush=True)
    return doc_ids


def platform_search(token, kb_id, q, k=5):
    r = httpx.post(f"{API}/knowledge-bases/{kb_id}/search", headers=_h(token),
                   json={"query": q, "top_k": k}, timeout=30)
    r.raise_for_status()
    seen, out = set(), []
    for h in r.json()["hits"]:
        d = h["doc_id"]
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def es_bm25(es, kb_id, q, k=5):
    r = es.search(index=settings.es_kb_index, size=k,
                  query={"bool": {"must": [{"match": {"content": q}}], "filter": [{"term": {"kb_id": kb_id}}]}})
    seen, out = set(), []
    for h in r["hits"]["hits"]:
        d = h["_source"]["doc_id"]
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def es_knn(es, kb_id, q, k=5):
    """真实向量 kNN: 用配置的 embedding API 把查询向量化, 再 kNN 检索 (与索引用同一模型)。"""
    vec = asyncio.run(embed_query(q))
    r = es.search(index=settings.es_kb_index, size=k,
                  knn={"field": "embedding", "query_vector": vec, "k": k, "num_candidates": 50,
                       "filter": {"term": {"kb_id": kb_id}}})
    seen, out = set(), []
    for h in r["hits"]["hits"]:
        d = h["_source"]["doc_id"]
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def real_vector_init():
    return None  # 已用平台真实 bge-m3, 不再需要本地 MiniLM 对照


def metrics(results_by_q, qrels_by_q, k=5):
    """results_by_q: {q: [doc_id...]}, qrels_by_q: {q: set(doc_id)}"""
    hit = mrr = rec = 0.0
    n = len(results_by_q)
    for q, res in results_by_q.items():
        rel = qrels_by_q[q]
        top = res[:k]
        inter = [d for d in top if d in rel]
        hit += 1 if inter else 0
        rec += len(inter) / len(rel) if rel else 0
        for rank, d in enumerate(top, 1):
            if d in rel:
                mrr += 1 / rank
                break
    return hit / n, mrr / n, rec / n


def main():
    print("=== 检索质量评测 ===", flush=True)
    # 载入 embedding 配置 (与平台服务一致, 使本进程的 embed_query 走配置的 API)
    from app.core.database import async_session_factory
    from app.core import embedding_config

    async def _load():
        async with async_session_factory() as db:
            await embedding_config.load_from_db(db)
    asyncio.run(_load())
    cfg = embedding_config.get()
    print(f"  embedding 来源: {'API ' + cfg['model'] if cfg['base_url'] and cfg['api_key'] else 'TEI/哈希'}", flush=True)

    token = login()
    print("  登录 OK", flush=True)
    kb_id = create_kb(token)
    print(f"  创建 KB: {kb_id}", flush=True)
    doc_ids = upload_docs(token, kb_id)
    qrels = {q: {doc_ids[idx]} for q, idx, _ in QUERIES}

    es = Elasticsearch(settings.es_url)
    rv = real_vector_init()

    methods = {
        "BM25-only (关键词)": lambda q: es_bm25(es, kb_id, q),
        "Vector-only (真实 bge-m3)": lambda q: es_knn(es, kb_id, q),
        "Hybrid 当前 (/search)": lambda q: platform_search(token, kb_id, q),
    }
    if rv:
        methods["Real-Vector (MiniLM)"] = lambda q: real_vector_search(rv, q)

    # 全量 + 按 kw/sem 拆分
    for subset, label in [("all", "全部"), ("kw", "关键词查询"), ("sem", "语义查询")]:
        print(f"\n--- {label} ({subset}) ---", flush=True)
        print(f"{'方法':<28} {'Hit@5':>8} {'MRR':>8} {'Recall@5':>10}", flush=True)
        for name, fn in methods.items():
            res, qrel = {}, {}
            for q, idx, t in QUERIES:
                if subset != "all" and t != subset:
                    continue
                try:
                    res[q] = fn(q)
                except Exception as e:
                    res[q] = []
                qrel[q] = qrels[q]
            if not res:
                continue
            h, m, r = metrics(res, qrel)
            print(f"{name:<28} {h:>8.2f} {m:>8.2f} {r:>10.2f}", flush=True)

    print("\n=== 结论 ===", flush=True)
    print("• Vector-only(哈希) 若接近随机 → 当前向量是摆设, 检索实为 BM25-only。", flush=True)
    print("• Hybrid 若 ≈ BM25-only → 向量未贡献, 语义检索缺失。", flush=True)
    print("• Real-Vector(若启用) 在语义查询上应显著高于 BM25 → 证明真实向量的价值。", flush=True)

    # 清理: 删除评测 KB
    try:
        httpx.delete(f"{API}/knowledge-bases/{kb_id}", headers=_h(token), timeout=30)
        print("  (已删除评测 KB)", flush=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
