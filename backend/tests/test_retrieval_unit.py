"""WP7 知识库检索链路单元测试。

覆盖:
- tei_client: 维度/数量校验、_embed_via_api 分批 64、数量不符降级 TEI
- es_client: bulk 错误解析 raise、ensure_kb_index 前置、NotFound 自愈重试、num_candidates 默认值
- common.token_utils.slice_tokens 与 document_service._split_and_append token 切片

全部通过 fake/monkeypatch 实现, 不依赖真实 TEI/ES/httpx 网络。
"""

import pytest

from app.core import es_client, tei_client
from app.core.config import settings
from common.token_utils import num_tokens_from_string, slice_tokens, truncate


# ── httpx fake ──

class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeHttpClient:
    """按队列返回响应的 httpx.AsyncClient 替身。"""

    def __init__(self, responses, calls):
        self._responses = responses
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self._calls.append({"url": url, "json": json})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _FakeResp(item)

    async def get(self, url):
        return _FakeResp({})


def _patch_httpx(monkeypatch, responses, calls):
    monkeypatch.setattr(
        tei_client.httpx, "AsyncClient",
        lambda *a, **k: _FakeHttpClient(responses, calls),
    )


def _no_embedding_api(monkeypatch):
    """关闭 Embedding API 配置, 强制走 TEI 路径。"""
    monkeypatch.setattr(
        "app.core.embedding_config.get",
        lambda: {"base_url": "", "api_key": "", "model": ""},
    )


# ── tei_client ──

async def test_embed_texts_dim_mismatch_raises(monkeypatch):
    """TEI 返回维度 != settings.embedding_dim 时应 raise (不静默兜底)。"""
    _no_embedding_api(monkeypatch)
    bad_dim = settings.embedding_dim + 1
    _patch_httpx(monkeypatch, [[[0.1] * bad_dim, [0.1] * bad_dim]], [])

    with pytest.raises(ValueError, match="维度不符"):
        await tei_client.embed_texts(["文本一", "文本二"])


async def test_embed_texts_count_mismatch_raises(monkeypatch):
    """TEI 返回数量与输入不符时应 raise。"""
    _no_embedding_api(monkeypatch)
    _patch_httpx(monkeypatch, [[[0.1] * settings.embedding_dim]], [])

    with pytest.raises(ValueError, match="数量不符"):
        await tei_client.embed_texts(["文本一", "文本二"])


async def test_embed_texts_tei_ok(monkeypatch):
    """TEI 正常返回时通过校验。"""
    _no_embedding_api(monkeypatch)
    _patch_httpx(monkeypatch, [[[0.1] * settings.embedding_dim] * 3], [])

    vectors = await tei_client.embed_texts(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == settings.embedding_dim for v in vectors)


async def test_embed_via_api_batches_64(monkeypatch):
    """Embedding API 应按 64 条分批调用。"""
    monkeypatch.setattr(
        "app.core.embedding_config.get",
        lambda: {"base_url": "http://api.test/v1", "api_key": "k", "model": "m"},
    )
    calls = []

    def make_response(n):
        return {"data": [{"index": i, "embedding": [0.1] * settings.embedding_dim} for i in range(n)]}

    # 130 条 → 64 + 64 + 2 三批
    responses = [make_response(64), make_response(64), make_response(2)]
    _patch_httpx(monkeypatch, responses, calls)

    vectors = await tei_client.embed_texts([f"text-{i}" for i in range(130)])
    assert len(vectors) == 130
    assert len(calls) == 3
    assert [len(c["json"]["input"]) for c in calls] == [64, 64, 2]


async def test_embed_via_api_count_mismatch_falls_back_to_tei(monkeypatch):
    """Embedding API 返回数量不符 → raise → embed_texts 降级到 TEI。"""
    monkeypatch.setattr(
        "app.core.embedding_config.get",
        lambda: {"base_url": "http://api.test/v1", "api_key": "k", "model": "m"},
    )
    calls = []
    responses = [
        {"data": [{"index": 0, "embedding": [0.1] * settings.embedding_dim}]},  # API 只回 1 条
        [[0.2] * settings.embedding_dim, [0.2] * settings.embedding_dim],       # TEI 正常
    ]
    _patch_httpx(monkeypatch, responses, calls)

    vectors = await tei_client.embed_texts(["x", "y"])
    assert len(vectors) == 2
    assert all(v[0] == pytest.approx(0.2) for v in vectors)
    assert len(calls) == 2  # API 1 次 + TEI 1 次
    assert "/embeddings" in calls[0]["url"]
    assert "/embed" in calls[1]["url"]


# ── es_client ──

class _FakeIndices:
    def __init__(self, exists=True):
        self._exists = exists
        self.create_called = 0

    async def exists(self, index):
        return self._exists

    async def create(self, index, body):
        self.create_called += 1
        self._exists = True


class _FakeES:
    def __init__(self, bulk_results=None, search_results=None, indices=None):
        self.indices = indices or _FakeIndices()
        self._bulk_results = list(bulk_results or [])
        self._search_results = list(search_results or [])
        self.search_calls = []

    async def bulk(self, operations, refresh=False):
        return self._bulk_results.pop(0)

    async def search(self, index, body):
        self.search_calls.append(body)
        item = self._search_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _chunk(i=0):
    return {
        "chunk_id": f"c-{i}", "kb_id": "kb-1", "doc_id": "d-1",
        "content": f"内容 {i}", "content_type": "text", "page": 0,
        "embedding": [0.1] * settings.embedding_dim, "metadata": {},
    }


async def test_index_chunks_bulk_raises_on_errors(monkeypatch):
    """bulk 响应含 error 条目时应解析错误并 raise。"""
    fake = _FakeES(bulk_results=[{
        "errors": True,
        "items": [
            {"index": {"_id": "c-0", "status": 201}},
            {"index": {"_id": "c-1", "error": {"type": "mapper_parsing_exception", "reason": "bad"}}},
        ],
    }])
    monkeypatch.setattr(es_client, "get_es_client", lambda: fake)

    with pytest.raises(RuntimeError, match="bulk 索引失败"):
        await es_client.index_chunks_bulk([_chunk(0), _chunk(1)])


async def test_index_chunks_bulk_ensures_index(monkeypatch):
    """bulk 前应确保索引存在, 缺失时自动创建。"""
    indices = _FakeIndices(exists=False)
    fake = _FakeES(
        bulk_results=[{"errors": False, "items": [{"index": {"status": 201}}]}],
        indices=indices,
    )
    monkeypatch.setattr(es_client, "get_es_client", lambda: fake)

    indexed = await es_client.index_chunks_bulk([_chunk(0)])
    assert indexed == 1
    assert indices.create_called == 1


async def test_hybrid_search_num_candidates_default(monkeypatch):
    """num_candidates 默认 max(200, top_k*10)。"""
    fake = _FakeES(search_results=[
        {"hits": {"hits": []}},
        {"hits": {"hits": []}},
    ])
    monkeypatch.setattr(es_client, "get_es_client", lambda: fake)

    await es_client.hybrid_search("kb-1", [0.1] * settings.embedding_dim, "查询", top_k=5)
    await es_client.hybrid_search("kb-1", [0.1] * settings.embedding_dim, "查询", top_k=50)

    assert fake.search_calls[0]["knn"]["num_candidates"] == 200   # max(200, 50)
    assert fake.search_calls[1]["knn"]["num_candidates"] == 500   # max(200, 500)


async def test_hybrid_search_notfound_retry(monkeypatch):
    """索引缺失 (NotFound) 时重建索引并重试一次。"""
    class FakeNotFound(Exception):
        pass

    monkeypatch.setattr(es_client, "NotFoundError", FakeNotFound)
    indices = _FakeIndices(exists=False)
    hit = {
        "_score": 0.9,
        "_source": {
            "chunk_id": "c-1", "doc_id": "d-1", "content": "命中内容",
            "content_type": "text", "page": 0, "metadata": {},
        },
    }
    fake = _FakeES(search_results=[FakeNotFound("index_not_found"), {"hits": {"hits": [hit]}}], indices=indices)
    monkeypatch.setattr(es_client, "get_es_client", lambda: fake)

    results = await es_client.hybrid_search("kb-1", [0.1] * settings.embedding_dim, "查询", top_k=5)
    assert len(fake.search_calls) == 2
    assert indices.create_called == 1
    assert results[0]["content"] == "命中内容"


# ── token 切片 ──

def test_slice_tokens_matches_truncate_prefix():
    """slice_tokens(s, 0, n) 应与 truncate(s, n) 一致。"""
    text = "知识库检索链路的 token 切片测试, 包含中文与 English mixed content。" * 3
    total = num_tokens_from_string(text)
    for n in (1, 5, total // 2, total):
        assert slice_tokens(text, 0, n) == truncate(text, n)


def test_slice_tokens_middle_window():
    """中间窗口切片的 token 数应等于 end-start。"""
    text = "第一段内容。第二段内容。第三段内容。第四段内容。第五段内容。" * 5
    total = num_tokens_from_string(text)
    start, end = total // 4, total // 2
    sliced = slice_tokens(text, start, end)
    assert num_tokens_from_string(sliced) == end - start


async def test_split_and_append_fixed_strategy():
    """_split_and_append 按 token 窗口切分, 步长 = chunk_size - overlap。"""
    from types import SimpleNamespace

    from app.services.document_service import _create_chunks

    # 构造超长文本块, 强制切分
    text = "切分测试句子。" * 200
    total = num_tokens_from_string(text)
    chunk_size, overlap = 64, 16
    assert total > chunk_size

    kb = SimpleNamespace(
        chunk_strategy=SimpleNamespace(value="fixed"),
        chunk_size=chunk_size,
        chunk_overlap=overlap,
    )
    chunks = _create_chunks([{"content": text, "content_type": "text", "page": 0}], kb)

    assert len(chunks) >= 2
    # 每个 chunk 的 token 数不超过 chunk_size
    for c in chunks:
        assert num_tokens_from_string(c["content"]) <= chunk_size
    # token_start 按 step 递增
    starts = [c["metadata"]["token_start"] for c in chunks]
    assert starts[0] == 0
    assert all(b - a == chunk_size - overlap for a, b in zip(starts, starts[1:]))
    # 末块 token_end 到达文本末尾
    assert chunks[-1]["metadata"]["token_end"] == total
