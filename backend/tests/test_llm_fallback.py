"""LLM 供应商层测试: 降级顺序 / 重试 / 流式 started 与 0 字节 / Key 热更新 / 解密失败兜底。"""

from types import SimpleNamespace

import httpx
import pytest

from app.core import llm_client, llm_config
from app.core.config import settings

MESSAGES = [{"role": "user", "content": "你好"}]


@pytest.fixture(autouse=True)
def _reset_llm_config_cache():
    """每个测试前后清空 llm_config 内存缓存, 避免用例间串扰。"""
    with llm_config._lock:
        llm_config._cache.update({"kaiweb": "", "openai": "", "anthropic": ""})
    yield
    with llm_config._lock:
        llm_config._cache.update({"kaiweb": "", "openai": "", "anthropic": ""})


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "http://test/chat/completions")
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=req, response=httpx.Response(status_code, request=req)
    )


# ── 降级顺序 ──


@pytest.mark.asyncio
async def test_fallback_order(monkeypatch):
    """Kaiweb 空结果 → OpenClaw 异常 → OpenAI 成功, 按顺序降级。"""
    calls = []

    async def fake_kaiweb(messages, model, base_url, api_key, provider, *a, **k):
        calls.append("kaiweb")
        return ""  # 空结果视为失败

    async def fake_openclaw(*a, **k):
        calls.append("openclaw")
        raise RuntimeError("openclaw down")

    async def fake_openai(messages, model, api_key, *a, **k):
        calls.append("openai")
        return "openai-ok"

    monkeypatch.setattr(llm_client, "_call_openai_compatible", fake_kaiweb)
    monkeypatch.setattr(llm_client, "_call_openclaw", fake_openclaw)
    monkeypatch.setattr(llm_client, "_call_openai", fake_openai)
    monkeypatch.setattr(settings, "kaiweb_api_key", "kw-key")
    monkeypatch.setattr(settings, "openai_api_key", "oa-key")

    result = await llm_client.chat(MESSAGES)
    assert result == "openai-ok"
    assert calls == ["kaiweb", "openclaw", "openai"]


# ── 5xx / 连接错误重试 ──


@pytest.mark.asyncio
async def test_retry_once_on_5xx(monkeypatch):
    """5xx 时 0.5s 退避重试一次, 第二次成功即返回。"""
    attempts = 0

    async def flaky(messages, model, base_url, api_key, provider, *a, **k):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _http_error(500)
        return "retried-ok"

    monkeypatch.setattr(llm_client, "_call_openai_compatible", flaky)
    monkeypatch.setattr(settings, "kaiweb_api_key", "kw-key")

    result = await llm_client.chat(MESSAGES)
    assert result == "retried-ok"
    assert attempts == 2


@pytest.mark.asyncio
async def test_no_retry_on_4xx(monkeypatch):
    """4xx 不重试, 直接降级到下一供应商。"""
    attempts = 0

    async def unauthorized(messages, model, base_url, api_key, provider, *a, **k):
        nonlocal attempts
        attempts += 1
        raise _http_error(401)

    async def fake_openclaw(*a, **k):
        return "openclaw-ok"

    monkeypatch.setattr(llm_client, "_call_openai_compatible", unauthorized)
    monkeypatch.setattr(llm_client, "_call_openclaw", fake_openclaw)
    monkeypatch.setattr(settings, "kaiweb_api_key", "kw-key")

    result = await llm_client.chat(MESSAGES)
    assert result == "openclaw-ok"
    assert attempts == 1


@pytest.mark.asyncio
async def test_retry_once_on_connect_error(monkeypatch):
    """连接错误重试一次后仍失败, 降级到下一供应商。"""
    attempts = 0

    async def unreachable(messages, model, base_url, api_key, provider, *a, **k):
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("connection refused")

    async def fake_openclaw(*a, **k):
        return "openclaw-ok"

    monkeypatch.setattr(llm_client, "_call_openai_compatible", unreachable)
    monkeypatch.setattr(llm_client, "_call_openclaw", fake_openclaw)
    monkeypatch.setattr(settings, "kaiweb_api_key", "kw-key")

    result = await llm_client.chat(MESSAGES)
    assert result == "openclaw-ok"
    assert attempts == 2


# ── 解密失败兜底 ──


def test_get_openai_key_decrypt_failure_falls_back(monkeypatch, caplog):
    """用户 Key 解密失败时按未配置处理, 回落全局 Key, 不把密文当明文用。"""
    user = SimpleNamespace(openai_api_key="not-a-valid-ciphertext", id="u1")
    monkeypatch.setattr(settings, "openai_api_key", "global-key")

    key = llm_client._get_openai_key(user)
    assert key == "global-key"
    assert "解密失败" in caplog.text


# ── 流式: started / 0 字节 / reasoning_content ──


@pytest.mark.asyncio
async def test_stream_zero_byte_falls_back(monkeypatch):
    """流式 0 字节视为失败, 继续降级到下一供应商。"""

    async def empty_stream(*a, **k):
        return
        yield  # pragma: no cover - 使其成为 async generator

    async def openclaw_stream(*a, **k):
        yield "hello"

    monkeypatch.setattr(llm_client, "_stream_openai_compatible", empty_stream)
    monkeypatch.setattr(llm_client, "_stream_openclaw", openclaw_stream)
    monkeypatch.setattr(settings, "kaiweb_api_key", "kw-key")

    chunks = [c async for c in llm_client.chat_stream(MESSAGES)]
    assert chunks == ["hello"]


@pytest.mark.asyncio
async def test_stream_no_fallback_after_started(monkeypatch):
    """已 yield 内容后流式失败不再降级 (避免重复内容), 异常向上抛出。"""
    called = {"openclaw": False}

    async def kaiweb_stream(*a, **k):
        yield "partial"
        raise RuntimeError("mid-stream boom")

    async def openclaw_stream(*a, **k):
        called["openclaw"] = True
        yield "x"

    monkeypatch.setattr(llm_client, "_stream_openai_compatible", kaiweb_stream)
    monkeypatch.setattr(llm_client, "_stream_openclaw", openclaw_stream)
    monkeypatch.setattr(settings, "kaiweb_api_key", "kw-key")

    chunks = []
    with pytest.raises(RuntimeError, match="mid-stream boom"):
        async for c in llm_client.chat_stream(MESSAGES):
            chunks.append(c)
    assert chunks == ["partial"]
    assert not called["openclaw"]


@pytest.mark.asyncio
async def test_stream_reasoning_content(monkeypatch):
    """SSE delta.content 为空时取 reasoning_content (推理模型兼容)。"""
    lines = [
        'data: {"choices":[{"delta":{"reasoning_content":"思考中"}}]}',
        'data: {"choices":[{"delta":{"content":"答案"}}]}',
        "data: [DONE]",
    ]

    class FakeResp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            for line in lines:
                yield line

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    chunks = [
        c
        async for c in llm_client._stream_openai_compatible(
            MESSAGES, "m", "http://x/v1", "k", "test", 0.7, 100, 5
        )
    ]
    assert chunks == ["思考中", "答案"]


# ── Key DB 热更新 ──


@pytest.mark.asyncio
async def test_chat_uses_hot_updated_key(db_session, monkeypatch):
    """llm_config.save 写入 DB 后, chat() 立即使用新 Key (内存缓存热更新)。"""
    captured = {}

    async def spy(messages, model, base_url, api_key, provider, *a, **k):
        captured["key"] = api_key
        return "ok"

    monkeypatch.setattr(llm_client, "_call_openai_compatible", spy)
    # settings 无 Key, 仅靠 DB 热更新生效
    monkeypatch.setattr(settings, "kaiweb_api_key", "")

    await llm_config.save(
        db_session, kaiweb_api_key="db-hot-key", openai_api_key="", anthropic_api_key=""
    )

    result = await llm_client.chat(MESSAGES)
    assert result == "ok"
    assert captured["key"] == "db-hot-key"


def test_llm_config_falls_back_to_settings(monkeypatch):
    """缓存为空时 get_key 回落 settings (.env)。"""
    monkeypatch.setattr(settings, "openai_api_key", "env-key")
    assert llm_config.get_key("openai") == "env-key"
    assert llm_config.status()["openai"] is True
    assert llm_config.status()["anthropic"] is False
