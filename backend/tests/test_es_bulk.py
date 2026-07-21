"""ES bulk 分批 + 429 重试单元测试 (生产事故修复: coordinating_operation_bytes / circuit_breaking)。

覆盖:
- 按条数 (≤100) 与估算字节 (≤5MB) 分批, 仅最后一批 refresh=True
- 429 / es_rejected_execution / circuit_breaking 可恢复错误指数退避重试
- 重试耗尽后 raise; 不可恢复错误不重试

全部 mock es.bulk / ensure_kb_index / asyncio.sleep, 不依赖真实 ES。
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from elastic_transport import ApiResponseMeta, NodeConfig
from elasticsearch import ApiError

from app.core import es_client


class _RecordingES:
    """记录 bulk 调用并按队列返回/抛错的 ES 替身。"""

    def __init__(self, outcomes):
        self.calls = []          # [{"operations": [...], "refresh": bool}, ...]
        self._outcomes = list(outcomes)

    async def bulk(self, operations, refresh=False):
        self.calls.append({"operations": operations, "refresh": refresh})
        item = self._outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(n):
    return {"errors": False, "items": [{"index": {"status": 201}} for _ in range(n)]}


def _api_error_429(error_type="es_rejected_execution_exception"):
    meta = ApiResponseMeta(
        status=429,
        http_version="1.1",
        headers={},
        duration=0.0,
        node=NodeConfig("http", "localhost", 9200),
    )
    return ApiError(error_type, meta=meta, body={"error": {"type": error_type}})


def _chunk(i=0, content_size=0):
    return {
        "chunk_id": f"c-{i}", "kb_id": "kb-1", "doc_id": "d-1",
        "content": "x" * content_size or f"内容 {i}",
        "content_type": "text", "page": 0,
        "embedding": [0.1, 0.2, 0.3],   # 小 embedding, 字节数靠 content 撑
        "metadata": {},
    }


def _patch_common(monkeypatch, es):
    """mock ensure_kb_index + get_es_client + asyncio.sleep (记录退避时长)。"""
    monkeypatch.setattr(es_client, "ensure_kb_index", AsyncMock())
    monkeypatch.setattr(es_client, "get_es_client", lambda: es)
    sleeps = []
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(side_effect=lambda d: sleeps.append(d)))
    return sleeps


def _batch_stats(call):
    """从一次 bulk 调用还原 (chunk 数, 估算字节数)。"""
    ops = call["operations"]
    sources = ops[1::2]
    nbytes = sum(len(json.dumps(s, ensure_ascii=False, default=str).encode("utf-8")) + 128 for s in sources)
    return len(sources), nbytes


# ── 分批逻辑 ──

async def test_bulk_batches_by_chunk_count(monkeypatch):
    """250 个小 chunk → 100 + 100 + 50 三批, 仅最后一批 refresh=True。"""
    es = _RecordingES([_ok(100), _ok(100), _ok(50)])
    sleeps = _patch_common(monkeypatch, es)

    indexed = await es_client.index_chunks_bulk([_chunk(i) for i in range(250)])

    assert indexed == 250
    assert len(es.calls) == 3
    counts = [_batch_stats(c)[0] for c in es.calls]
    assert counts == [100, 100, 50]
    assert all(n <= es_client._BULK_MAX_CHUNKS for n in counts)
    assert [c["refresh"] for c in es.calls] == [False, False, True]
    assert sleeps == []  # 无重试


async def test_bulk_batches_by_estimated_bytes(monkeypatch):
    """大 content 撑字节数 → 按 5MB 上限分批, 每批 ≤ 上限。"""
    # 每 chunk ≈ 600KB, 5MB / 600KB = 8 条/批 → 20 条 = 8 + 8 + 4
    es = _RecordingES([_ok(8), _ok(8), _ok(4)])
    _patch_common(monkeypatch, es)

    chunks = [_chunk(i, content_size=600 * 1024) for i in range(20)]
    indexed = await es_client.index_chunks_bulk(chunks)

    assert indexed == 20
    assert len(es.calls) == 3
    counts = [_batch_stats(c)[0] for c in es.calls]
    assert counts == [8, 8, 4]
    for c in es.calls:
        _, nbytes = _batch_stats(c)
        assert nbytes <= es_client._BULK_MAX_BYTES
    assert [c["refresh"] for c in es.calls] == [False, False, True]


async def test_bulk_single_batch_still_refresh_true(monkeypatch):
    """单批 (少量 chunk) 仍 refresh=True, 行为与旧版一致。"""
    es = _RecordingES([_ok(2)])
    _patch_common(monkeypatch, es)

    indexed = await es_client.index_chunks_bulk([_chunk(0), _chunk(1)])
    assert indexed == 2
    assert len(es.calls) == 1
    assert es.calls[0]["refresh"] is True


async def test_bulk_empty_chunks_no_call(monkeypatch):
    """空列表直接返回 0, 不触达 ES。"""
    es = _RecordingES([])
    _patch_common(monkeypatch, es)
    assert await es_client.index_chunks_bulk([]) == 0
    assert es.calls == []


# ── 429 重试 ──

async def test_bulk_retry_on_429_then_success(monkeypatch):
    """前两次 ApiError(429), 第三次成功 → 最终成功且调用 3 次, 退避 2s/5s。"""
    es = _RecordingES([_api_error_429(), _api_error_429(), _ok(3)])
    sleeps = _patch_common(monkeypatch, es)

    indexed = await es_client.index_chunks_bulk([_chunk(i) for i in range(3)])

    assert indexed == 3
    assert len(es.calls) == 3
    assert [c.args[0] for c in asyncio.sleep.call_args_list] == [2.0, 5.0]


async def test_bulk_retry_on_circuit_breaking(monkeypatch):
    """circuit_breaking_exception (429) 同样可恢复。"""
    es = _RecordingES([_api_error_429("circuit_breaking_exception"), _ok(1)])
    _patch_common(monkeypatch, es)

    indexed = await es_client.index_chunks_bulk([_chunk(0)])
    assert indexed == 1
    assert len(es.calls) == 2


async def test_bulk_retry_exhausted_raises(monkeypatch):
    """重试 3 次仍 429 → 耗尽后原样 raise, 共 4 次调用。"""
    es = _RecordingES([_api_error_429()] * 4)
    _patch_common(monkeypatch, es)

    with pytest.raises(ApiError):
        await es_client.index_chunks_bulk([_chunk(0)])

    assert len(es.calls) == 1 + len(es_client._BULK_RETRY_DELAYS)
    assert [c.args[0] for c in asyncio.sleep.call_args_list] == list(es_client._BULK_RETRY_DELAYS)


async def test_bulk_non_recoverable_error_no_retry(monkeypatch):
    """非 429 类错误 (如 400 mapper_parsing) 不重试, 直接 raise。"""
    meta = ApiResponseMeta(
        status=400, http_version="1.1", headers={}, duration=0.0,
        node=NodeConfig("http", "localhost", 9200),
    )
    bad = ApiError("mapper_parsing_exception", meta=meta, body={})
    es = _RecordingES([bad])
    _patch_common(monkeypatch, es)

    with pytest.raises(ApiError):
        await es_client.index_chunks_bulk([_chunk(0)])
    assert len(es.calls) == 1


async def test_bulk_retry_applies_per_batch(monkeypatch):
    """重试按批次独立: 第一批失败重试成功, 第二批一次成功。"""
    # 120 条 → 100 + 20 两批; 第一批先 429 再成功
    es = _RecordingES([_api_error_429(), _ok(100), _ok(20)])
    _patch_common(monkeypatch, es)

    indexed = await es_client.index_chunks_bulk([_chunk(i) for i in range(120)])

    assert indexed == 120
    assert len(es.calls) == 3
    # 第一批两次调用都 refresh=False, 第二批 refresh=True
    assert [c["refresh"] for c in es.calls] == [False, False, True]
