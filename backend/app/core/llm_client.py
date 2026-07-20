"""LLM 统一客户端。

对齐 PRD 第 7 节: OpenClaw 优先 → OpenAI fallback → Anthropic fallback。
通过 httpx 直调 HTTP API, 不引入 langchain/openai SDK。
"""

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings
from app.utils.crypto import decrypt

logger = logging.getLogger("claw.llm")


async def chat(
    messages: list[dict[str, str]],
    model: str = "default",
    user=None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = 120.0,
) -> str:
    """调用 LLM 服务, 返回文本回复。

    优先级:
      1. OpenClaw (本地, settings.openclaw_url) — 数据不出域
      2. OpenAI (用户 API Key 或全局配置)
      3. Anthropic (用户 API Key 或全局配置)

    Args:
        messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
        model: 模型标识 (OpenClaw 自定义, 或 OpenAI model name)
        user: User 对象 (读取加密的 API Key)
        temperature: 采样温度
        max_tokens: 最大输出 token
        timeout: HTTP 超时

    Returns:
        LLM 回复文本
    """
    # 1. OpenClaw owns agent context, tools, and provider routing.
    try:
        result = await _call_openclaw(messages, model, temperature, max_tokens, timeout)
        if result:
            logger.info("LLM 调用成功: OpenClaw (model=%s)", model)
            return result
    except Exception as e:
        logger.warning("OpenClaw 调用失败, 尝试 fallback: %s", e)

    # 2. Direct Kaiweb is retained as a fallback when OpenClaw is unavailable.
    if settings.kaiweb_api_key:
        try:
            result = await _call_openai_compatible(
                messages, _resolve_kaiweb_model(model), settings.kaiweb_base_url, settings.kaiweb_api_key,
                "kaiweb", temperature, max_tokens, timeout,
            )
            if result:
                logger.info("LLM 调用成功: Kaiweb fallback (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("Kaiweb 调用失败, 尝试 fallback: %s", e)

    # 3. 尝试 OpenAI
    openai_key = _get_openai_key(user)
    if openai_key:
        try:
            result = await _call_openai(messages, model, openai_key, temperature, max_tokens, timeout)
            if result:
                logger.info("LLM 调用成功: OpenAI (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("OpenAI 调用失败, 尝试 fallback: %s", e)

    # 4. 尝试 Anthropic
    anthropic_key = settings.anthropic_api_key
    if anthropic_key:
        try:
            result = await _call_anthropic(messages, model, anthropic_key, temperature, max_tokens, timeout)
            if result:
                logger.info("LLM 调用成功: Anthropic (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("Anthropic 调用失败: %s", e)

    # 5. dev 兜底: 所有真实供应商不可用时, 返回模板化回复 (仅开发环境)
    if settings.environment == "dev":
        logger.warning("所有真实 LLM 供应商不可用, dev 回退 mock 回复")
        return _call_mock(messages, model)

    raise RuntimeError("所有 LLM 供应商均不可用。请检查 Kaiweb/OpenClaw 服务状态或配置 API Key。")


def _call_mock(messages: list[dict], model: str) -> str:
    """dev 兜底 LLM: 基于最后一条用户消息生成模板化回复。

    离线演示用, 保证工作流 LLM 节点可执行; 生产环境不应出现。
    """
    user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break
    preview = user_content[:200].replace("\n", " ")
    return (
        f"[Mock LLM · {model}] 已收到您的请求（离线兜底，非真实模型推理）。\n\n"
        f"输入预览：{preview}\n\n"
        "提示：配置 OpenAI/Anthropic API Key 或启动本地 OpenClaw 服务后，将获得真实模型回复。"
    )


def _get_openai_key(user) -> str:
    """获取 OpenAI API Key: 优先用户配置, 其次全局。"""
    if user and user.openai_api_key:
        try:
            return decrypt(user.openai_api_key)
        except Exception:
            return user.openai_api_key
    return settings.openai_api_key


async def _call_openclaw(
    messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float
) -> str:
    """调用 OpenClaw 的 OpenAI 兼容 Chat Completions API。"""
    target, headers = _openclaw_request(model)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.openclaw_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": target,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenClaw 返回无效的 Chat Completions 响应")
        content = choices[0].get("message", {}).get("content", "")
        return content if isinstance(content, str) else ""


def _openclaw_request(model: str) -> tuple[str, dict[str, str]]:
    """Map platform model names to OpenClaw's agent-first model contract."""
    headers = {"Content-Type": "application/json"}
    if settings.openclaw_token:
        headers["Authorization"] = f"Bearer {settings.openclaw_token}"

    if model in ("", "default", "openclaw", "hermes", "kaiweb", "mock"):
        return "openclaw/default", headers
    if model.startswith(("openclaw/", "openclaw:", "agent:")):
        return model, headers

    # The OpenClaw `model` field selects an agent. Provider models are overrides.
    headers["x-openclaw-model"] = model
    return "openclaw/default", headers


async def _call_openai(
    messages: list[dict], model: str, api_key: str, temperature: float, max_tokens: int, timeout: float
) -> str:
    """调用 OpenAI Chat Completions API。"""
    # 如果 model 是 "default" 或 OpenClaw 自定义名, 替换为 OpenAI 模型
    if model in ("default", "openclaw", "hermes", "kaiweb", "mock"):
        model = "gpt-4o-mini"

    return await _call_openai_compatible(
        messages, model, "https://api.openai.com/v1", api_key,
        "openai", temperature, max_tokens, timeout,
    )


def _resolve_kaiweb_model(model: str) -> str:
    """将平台内部模型标识映射为 Kaiweb 网关实际可用的模型名。"""
    if model in ("default", "openclaw", "hermes", "kaiweb", "mock", ""):
        return settings.kaiweb_model
    return model


async def _call_openai_compatible(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    provider: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    """调用任意 OpenAI 兼容的 /v1/chat/completions 端点 (OpenAI / Kaiweb / 自建网关)。

    兼容推理模型: 若 content 为空但 reasoning_content 有值 (finish_reason=length),
    回退返回 reasoning_content, 避免被上层误判为失败。
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        content = msg.get("content", "") or ""
        if content:
            return content
        # 推理模型兜底: content 为空时返回 reasoning_content
        reasoning = msg.get("reasoning_content", "") or ""
        return reasoning


async def _call_anthropic(
    messages: list[dict], model: str, api_key: str, temperature: float, max_tokens: int, timeout: float
) -> str:
    """调用 Anthropic Messages API。"""
    if model in ("default", "openclaw", "hermes", "gpt-4o-mini"):
        model = "claude-sonnet-4-20250514"

    # 转换 messages 格式: 分离 system, 其余传 messages
    system_content = ""
    api_messages = []
    for msg in messages:
        if msg["role"] == "system":
            system_content += msg["content"] + "\n"
        else:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "messages": api_messages,
                "system": system_content.strip() or None,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("content", [{}])[0].get("text", "")


async def health_check() -> bool:
    """检查 OpenClaw Chat Completions 能力，而不只检查进程存活。"""
    try:
        headers = {}
        if settings.openclaw_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_token}"
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(f"{settings.openclaw_url}/v1/models", headers=headers)
            if resp.status_code != 200:
                return False
            data = resp.json()
            models = data.get("data") if isinstance(data, dict) else None
            return isinstance(models, list) and any(
                isinstance(item, dict) and item.get("id") for item in models
            )
    except Exception:
        return False


async def kaiweb_health_check() -> bool:
    """Kaiweb 网关连通性 + Key 有效性检查 (GET /v1/models)。"""
    if not settings.kaiweb_api_key:
        return False
    try:
        timeout = httpx.Timeout(20.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{settings.kaiweb_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {settings.kaiweb_api_key}"},
            )
            if resp.status_code >= 400:
                return False
            data = resp.json()
            return isinstance(data, dict) and isinstance(data.get("data"), list)
    except Exception:
        return False


async def chat_stream(
    messages: list[dict[str, str]],
    model: str = "default",
    user=None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout: float = 120.0,
) -> AsyncGenerator[str, None]:
    """流式调用 LLM, yield 文本增量。

    优先 OpenClaw SSE 流式, fallback 到 OpenAI 流式。
    如果流式不可用, 降级为非流式调用并一次性 yield 完整回复。
    """
    # 1. OpenClaw owns the primary streaming path.
    emitted = False
    try:
        async for chunk in _stream_openclaw(messages, model, temperature, max_tokens, timeout):
            emitted = True
            yield chunk
        if not emitted:
            raise RuntimeError("OpenClaw 流式响应未包含文本")
        return
    except Exception as e:
        if emitted:
            raise
        logger.warning("OpenClaw 流式失败, 尝试 fallback: %s", e)

    # 2. Direct Kaiweb streaming fallback.
    if settings.kaiweb_api_key:
        emitted = False
        try:
            async for chunk in _stream_openai_compatible(
                messages, _resolve_kaiweb_model(model), settings.kaiweb_base_url, settings.kaiweb_api_key, "kaiweb",
                temperature, max_tokens, timeout,
            ):
                emitted = True
                yield chunk
            if not emitted:
                raise RuntimeError("Kaiweb 流式响应未包含文本")
            return
        except Exception as e:
            if emitted:
                raise
            logger.warning("Kaiweb 流式失败, 尝试 fallback: %s", e)

    # 3. 尝试 OpenAI 流式
    openai_key = _get_openai_key(user)
    if openai_key:
        emitted = False
        try:
            async for chunk in _stream_openai(messages, model, openai_key, temperature, max_tokens, timeout):
                emitted = True
                yield chunk
            if not emitted:
                raise RuntimeError("OpenAI 流式响应未包含文本")
            return
        except Exception as e:
            if emitted:
                raise
            logger.warning("OpenAI 流式失败, 尝试非流式: %s", e)

    # 4. 降级: 非流式调用, 一次性 yield
    result = await chat(messages, model=model, user=user, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    yield result


async def _stream_openclaw(
    messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float
) -> AsyncGenerator[str, None]:
    """OpenClaw SSE 流式调用。"""
    target, headers = _openclaw_request(model)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{settings.openclaw_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": target,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].lstrip()
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
                except json.JSONDecodeError:
                    continue


async def _stream_openai(
    messages: list[dict], model: str, api_key: str, temperature: float, max_tokens: int, timeout: float
) -> AsyncGenerator[str, None]:
    """OpenAI SSE 流式调用。"""
    if model in ("default", "openclaw", "hermes", "kaiweb", "mock"):
        model = "gpt-4o-mini"

    async for chunk in _stream_openai_compatible(
        messages, model, "https://api.openai.com/v1", api_key, "openai",
        temperature, max_tokens, timeout,
    ):
        yield chunk


async def _stream_openai_compatible(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str,
    provider: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> AsyncGenerator[str, None]:
    """任意 OpenAI 兼容端点的 SSE 流式调用 (OpenAI / Kaiweb / 自建网关)。"""
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].lstrip()
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
                except json.JSONDecodeError:
                    continue


async def list_models() -> list[dict]:
    """列出可用模型。优先 Kaiweb (真实网关), 其次 OpenClaw, 最后预定义列表。"""
    # 1. Kaiweb (配置 Key 时拉取真实模型列表)
    if settings.kaiweb_api_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.kaiweb_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.kaiweb_api_key}"},
                )
                if resp.status_code < 400:
                    data = resp.json()
                    models = data.get("data", [])
                    kaiweb_models = [
                        {"id": m.get("id", ""), "provider": "kaiweb", "name": m.get("id", "")}
                        for m in models
                    ]
                    if kaiweb_models:
                        return kaiweb_models
        except Exception as e:
            logger.warning("Kaiweb 模型列表拉取失败: %s", e)

    # 2. OpenClaw
    try:
        headers = {}
        if settings.openclaw_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_token}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.openclaw_url}/v1/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", [])
                openclaw_models = [
                    {"id": m.get("id", ""), "provider": "openclaw", "name": m.get("id", "")}
                    for m in models if isinstance(m, dict) and m.get("id")
                ]
                if openclaw_models:
                    return openclaw_models
    except Exception:
        pass

    # 3. 预定义模型列表
    return [
        {"id": "default", "provider": "kaiweb", "name": "默认 (Kaiweb 网关)"},
        {"id": settings.kaiweb_model, "provider": "kaiweb", "name": settings.kaiweb_model},
        {"id": "gpt-4o-mini", "provider": "openai", "name": "GPT-4o mini"},
        {"id": "claude-sonnet-4-20250514", "provider": "anthropic", "name": "Claude Sonnet 4"},
        {"id": "mock", "provider": "mock", "name": "Mock (开发兜底)"},
    ]
