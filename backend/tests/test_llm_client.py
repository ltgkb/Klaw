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
    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", True)
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
    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", True)
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
    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", True)
    monkeypatch.setattr(llm_client, "_call_openclaw", openclaw)
    monkeypatch.setattr(llm_client, "_call_openai_compatible", unexpected_kaiweb)

    result = await llm_client.chat([{"role": "user", "content": "hello"}])

    assert result == "from claw"


@pytest.mark.asyncio
async def test_default_chat_skips_unconfigured_openclaw(monkeypatch):
    """Compose dev 模式禁用 chat 时，默认请求应立即进入显式 Mock，不等待网关上游。"""
    async def unexpected_openclaw(*args, **kwargs):
        raise AssertionError("disabled default routing must not call OpenClaw")

    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", False)
    monkeypatch.setattr(llm_client, "_call_openclaw", unexpected_openclaw)

    result = await llm_client.chat([{"role": "user", "content": "hello"}])

    assert result.startswith("[Mock LLM")


def test_explicit_openclaw_model_still_probes_disabled_default_route(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", False)

    assert llm_client._should_try_openclaw("default") is False
    assert llm_client._should_try_openclaw("mock") is False
    assert llm_client._should_try_openclaw("openclaw") is True
    assert llm_client._should_try_openclaw("openclaw/main") is True


def test_hermes_routing_requires_enablement_or_explicit_model(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "hermes_chat_enabled", False)

    assert llm_client._should_try_hermes("default") is False
    assert llm_client._should_try_hermes("hermes") is True
    assert llm_client._should_try_hermes("hermes/hermes-agent") is True
    assert llm_client._hermes_model("hermes/hermes-agent") == "hermes-agent"


@pytest.mark.asyncio
async def test_enabled_hermes_is_real_nonstream_fallback(monkeypatch):
    calls = []

    async def hermes_compatible(messages, model, base_url, api_key, provider, *args, **kwargs):
        calls.append((model, base_url, api_key, provider))
        return "from hermes"

    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", False)
    monkeypatch.setattr(llm_client.settings, "hermes_chat_enabled", True)
    monkeypatch.setattr(llm_client.settings, "hermes_url", "http://hermes:8642")
    monkeypatch.setattr(llm_client.settings, "hermes_api_server_key", "hermes-secret")
    monkeypatch.setattr(llm_client, "_call_openai_compatible", hermes_compatible)

    result = await llm_client.chat([{"role": "user", "content": "hello"}])

    assert result == "from hermes"
    assert calls == [("hermes-agent", "http://hermes:8642/v1", "hermes-secret", "hermes")]


@pytest.mark.asyncio
async def test_enabled_hermes_streams_before_cloud_fallback(monkeypatch):
    providers = []

    async def hermes_stream(messages, model, base_url, api_key, provider, *args, **kwargs):
        providers.append(provider)
        yield "hermes-stream"

    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", False)
    monkeypatch.setattr(llm_client.settings, "hermes_chat_enabled", True)
    monkeypatch.setattr(llm_client.settings, "hermes_api_server_key", "hermes-secret")
    monkeypatch.setattr(llm_client, "_stream_openai_compatible", hermes_stream)

    chunks = [
        chunk
        async for chunk in llm_client.chat_stream([{"role": "user", "content": "hello"}])
    ]

    assert chunks == ["hermes-stream"]
    assert providers == ["hermes"]


def test_hermes_model_hidden_until_chat_is_enabled(monkeypatch):
    base = [{"id": "default", "provider": "mock", "name": "Default"}]
    monkeypatch.setattr(llm_client.settings, "hermes_chat_enabled", False)
    assert llm_client._with_hermes_model(base) == base

    monkeypatch.setattr(llm_client.settings, "hermes_chat_enabled", True)
    models = llm_client._with_hermes_model(base)
    assert models[-1]["id"] == "hermes/hermes-agent"
    assert models[-1]["provider"] == "hermes"


@pytest.mark.asyncio
async def test_model_discovery_hides_unconfigured_providers(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "openclaw_chat_enabled", False)
    monkeypatch.setattr(llm_client.settings, "hermes_chat_enabled", False)
    monkeypatch.setattr(llm_client.settings, "environment", "dev")
    monkeypatch.setattr(llm_client.llm_config, "get_key", lambda _provider: "")

    models = await llm_client.list_models()

    assert [(model["id"], model["provider"]) for model in models] == [
        ("default", "auto"),
        ("mock", "mock"),
    ]


def test_openclaw_model_contract(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "openclaw_token", "secret")

    target, headers = llm_client._openclaw_request("default")
    assert target == "openclaw/default"
    assert headers["Authorization"] == "Bearer secret"
    assert "x-openclaw-model" not in headers

    target, headers = llm_client._openclaw_request("openai/gpt-4o-mini")
    assert target == "openclaw/default"
    assert headers["x-openclaw-model"] == "openai/gpt-4o-mini"


def _stub_calculator_tool(monkeypatch):
    """合并后的 call_tool 会先经 discover_tools 校验工具存在 (main 侧行为);
    打桩让 "calculator" 通过校验, 使测试聚焦 OpenClaw 调用契约本身。"""
    from types import SimpleNamespace

    from app.services import local_agent_service

    async def fake_discover():
        return [SimpleNamespace(id="calculator")]

    monkeypatch.setattr(local_agent_service, "discover_tools", fake_discover)
    return local_agent_service


@pytest.mark.asyncio
async def test_openclaw_tool_invoke_requires_ok_response(monkeypatch):
    from app.services import local_agent_service

    _stub_calculator_tool(monkeypatch)

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

    _stub_calculator_tool(monkeypatch)

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
