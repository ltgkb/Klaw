"""LLM provider routing and streaming regression tests."""

import pytest

from app.core import llm_client


@pytest.mark.asyncio
async def test_empty_openclaw_stream_falls_back_to_kaiweb(monkeypatch):
    async def empty_stream(*args, **kwargs):
        if False:
            yield ""

    async def fallback_stream(*args, **kwargs):
        yield "fallback"

    monkeypatch.setattr(llm_client.settings, "kaiweb_api_key", "test-key")
    monkeypatch.setattr(llm_client, "_stream_openclaw", empty_stream)
    monkeypatch.setattr(llm_client, "_stream_openai_compatible", fallback_stream)

    chunks = [
        chunk
        async for chunk in llm_client.chat_stream(
            [{"role": "user", "content": "hello"}]
        )
    ]

    assert chunks == ["fallback"]


@pytest.mark.asyncio
async def test_partial_stream_failure_does_not_duplicate_from_fallback(monkeypatch):
    fallback_called = False

    async def partial_stream(*args, **kwargs):
        yield "partial"
        raise RuntimeError("connection lost")

    async def fallback_stream(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        yield "duplicate"

    monkeypatch.setattr(llm_client.settings, "kaiweb_api_key", "test-key")
    monkeypatch.setattr(llm_client, "_stream_openclaw", partial_stream)
    monkeypatch.setattr(llm_client, "_stream_openai_compatible", fallback_stream)

    chunks = []
    with pytest.raises(RuntimeError, match="connection lost"):
        async for chunk in llm_client.chat_stream(
            [{"role": "user", "content": "hello"}]
        ):
            chunks.append(chunk)

    assert chunks == ["partial"]
    assert fallback_called is False


@pytest.mark.asyncio
async def test_non_streaming_prefers_openclaw_over_direct_kaiweb(monkeypatch):
    async def openclaw(*args, **kwargs):
        return "from claw"

    async def unexpected_kaiweb(*args, **kwargs):
        raise AssertionError("direct Kaiweb must not run before OpenClaw")

    monkeypatch.setattr(llm_client.settings, "kaiweb_api_key", "test-key")
    monkeypatch.setattr(llm_client, "_call_openclaw", openclaw)
    monkeypatch.setattr(llm_client, "_call_openai_compatible", unexpected_kaiweb)

    result = await llm_client.chat([{"role": "user", "content": "hello"}])

    assert result == "from claw"


def test_openclaw_model_contract(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "openclaw_token", "secret")

    target, headers = llm_client._openclaw_request("default")
    assert target == "openclaw/default"
    assert headers["Authorization"] == "Bearer secret"
    assert "x-openclaw-model" not in headers

    target, headers = llm_client._openclaw_request("openai/gpt-4o-mini")
    assert target == "openclaw/default"
    assert headers["x-openclaw-model"] == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_openclaw_tool_invoke_requires_ok_response(monkeypatch):
    from app.services import local_agent_service

    requests = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"answer": 42}}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            requests.append((url, headers, json))
            return FakeResponse()

    monkeypatch.setattr(local_agent_service.httpx, "AsyncClient", FakeClient)
    result = await local_agent_service.call_tool("calculator", {"value": 21})

    assert result == {
        "tool_id": "calculator",
        "success": True,
        "result": {"answer": 42},
        "source": "openclaw",
    }
    assert requests[0][0].endswith("/tools/invoke")
    assert requests[0][2] == {"tool": "calculator", "args": {"value": 21}}


@pytest.mark.asyncio
async def test_openclaw_tool_invoke_rejects_non_json_success(monkeypatch):
    from app.services import local_agent_service

    class FakeResponse:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(local_agent_service.httpx, "AsyncClient", FakeClient)
    result = await local_agent_service.call_tool("calculator", {})

    assert result["success"] is False
    assert result["source"] == "mock"
    assert result["error"] == "OpenClaw 工具服务不可用 (ValueError)"
