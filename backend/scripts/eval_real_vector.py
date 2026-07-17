"""本地真实向量评测 (不依赖平台/ES)。

用与 eval_retrieval.py 相同的数据集, 用真实语义向量(paraphrase-multilingual-MiniLM-L12-v2)
做检索, 产出 Hit@5/MRR/Recall@5, 与远端 BM25/哈希向量数字对比。
用法 (Mac 本地): cd backend && PYTHONPATH=$PWD uv run python scripts/eval_real_vector.py
"""

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

QUERIES = [
    ("怎么申请退款", 0, "kw"), ("如何把钱退回来", 0, "sem"),
    ("几天能送到", 1, "sem"), ("标准快递要多久", 1, "sem"),
    ("怎么注销账户", 2, "kw"), ("账号怎么彻底删除", 2, "sem"),
    ("怎么升级会员", 3, "kw"), ("消费多少能成金卡", 3, "kw"),
    ("怎么开发票", 4, "kw"), ("增值税专票怎么开", 4, "sem"),
    ("忘记密码怎么办", 5, "kw"), ("登不进去如何重置", 5, "sem"),
    ("保修期多久", 6, "kw"), ("电子产品坏了能修吗", 6, "sem"),
    ("积分怎么用", 7, "kw"), ("100分能换什么", 7, "sem"),
    ("怎么取消订单", 8, "kw"), ("发货了还能退吗", 8, "sem"),
    ("你们会泄露我的信息吗", 9, "sem"), ("个人信息安全吗", 9, "sem"),
]


def metrics(items, k=5):
    """items: list of (ranked_doc_indices, relevant_index)"""
    hit = mrr = rec = 0.0
    n = len(items)
    for ranked, rel in items:
        top = ranked[:k]
        hit += 1 if rel in top else 0
        rec += (1 if rel in top else 0)  # 单相关
        for r, d in enumerate(top, 1):
            if d == rel:
                mrr += 1 / r
                break
    return hit / n, mrr / n, rec / n


def main():
    import numpy as np
    from sentence_transformers import SentenceTransformer
    print("加载真实向量模型 paraphrase-multilingual-MiniLM-L12-v2 ...", flush=True)
    m = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    doc_emb = m.encode(DOCS, normalize_embeddings=True)
    print("编码完成, doc_emb:", doc_emb.shape, flush=True)

    for subset, label in [("all", "全部"), ("kw", "关键词查询"), ("sem", "语义查询")]:
        items = []
        for q, idx, t in QUERIES:
            if subset != "all" and t != subset:
                continue
            qv = m.encode([q], normalize_embeddings=True)[0]
            sims = doc_emb @ qv
            ranked = list(np.argsort(-sims))
            items.append((ranked, idx))
        if not items:
            continue
        h, mr, r = metrics(items)
        print(f"{label:<10} Hit@5={h:.2f}  MRR={mr:.2f}  Recall@5={r:.2f}", flush=True)


if __name__ == "__main__":
    main()
