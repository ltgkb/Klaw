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
    # 1. 尝试 OpenClaw (本地优先)
    try:
        result = await _call_openclaw(messages, model, temperature, max_tokens, timeout)
        if result:
            logger.info("LLM 调用成功: OpenClaw (model=%s)", model)
            return result
    except Exception as e:
        logger.warning("OpenClaw 调用失败, 尝试 fallback: %s", e)

    # 2. 尝试 OpenAI
    openai_key = _get_openai_key(user)
    if openai_key:
        try:
            result = await _call_openai(messages, model, openai_key, temperature, max_tokens, timeout)
            if result:
                logger.info("LLM 调用成功: OpenAI (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("OpenAI 调用失败, 尝试 fallback: %s", e)

    # 3. 尝试 Anthropic
    anthropic_key = settings.anthropic_api_key
    if anthropic_key:
        try:
            result = await _call_anthropic(messages, model, anthropic_key, temperature, max_tokens, timeout)
            if result:
                logger.info("LLM 调用成功: Anthropic (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("Anthropic 调用失败: %s", e)

    raise RuntimeError("所有 LLM 供应商均不可用。请检查 OpenClaw 服务状态或配置 API Key。")


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
    """调用 OpenClaw HTTP API。

    OpenClaw gateway 支持 OpenAI 兼容的 /v1/chat/completions 端点 (需 auth token)。
    """
    headers = {"Content-Type": "application/json"}
    if settings.openclaw_token:
        headers["Authorization"] = f"Bearer {settings.openclaw_token}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            f"{settings.openclaw_url}/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


async def _call_openai(
    messages: list[dict], model: str, api_key: str, temperature: float, max_tokens: int, timeout: float
) -> str:
    """调用 OpenAI Chat Completions API。"""
    # 如果 model 是 "default" 或 OpenClaw 自定义名, 替换为 OpenAI 模型
    if model in ("default", "openclaw", "hermes"):
        model = "gpt-4o-mini"

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
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
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")


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
    """OpenClaw 连通性检查 (含 auth token)。"""
    try:
        headers = {}
        if settings.openclaw_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_token}"
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.openclaw_url}/health", headers=headers)
            return resp.status_code < 500
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
    # 1. 尝试 OpenClaw 流式
    try:
        async for chunk in _stream_openclaw(messages, model, temperature, max_tokens, timeout):
            yield chunk
        return
    except Exception as e:
        logger.warning("OpenClaw 流式失败, 尝试 fallback: %s", e)

    # 2. 尝试 OpenAI 流式
    openai_key = _get_openai_key(user)
    if openai_key:
        try:
            async for chunk in _stream_openai(messages, model, openai_key, temperature, max_tokens, timeout):
                yield chunk
            return
        except Exception as e:
            logger.warning("OpenAI 流式失败, 尝试非流式: %s", e)

    # 3. 降级: 非流式调用, 一次性 yield
    result = await chat(messages, model=model, user=user, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    yield result


async def _stream_openclaw(
    messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float
) -> AsyncGenerator[str, None]:
    """OpenClaw SSE 流式调用。"""
    headers = {"Content-Type": "application/json"}
    if settings.openclaw_token:
        headers["Authorization"] = f"Bearer {settings.openclaw_token}"

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{settings.openclaw_url}/v1/chat/completions",
            headers=headers,
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
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
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
    if model in ("default", "openclaw", "hermes"):
        model = "gpt-4o-mini"

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            "https://api.openai.com/v1/chat/completions",
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
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
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
    """列出 OpenClaw 可用模型。失败返回预定义列表。"""
    try:
        headers = {}
        if settings.openclaw_token:
            headers["Authorization"] = f"Bearer {settings.openclaw_token}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.openclaw_url}/v1/models", headers=headers)
            if resp.status_code < 400:
                data = resp.json()
                models = data.get("data", [])
                return [{"id": m.get("id", ""), "provider": "openclaw", "name": m.get("id", "")} for m in models]
    except Exception:
        pass

    # 预定义模型列表
    return [
        {"id": "default", "provider": "openclaw", "name": "默认 (OpenClaw 优先)"},
        {"id": "gpt-4o-mini", "provider": "openai", "name": "GPT-4o mini"},
        {"id": "claude-sonnet-4-20250514", "provider": "anthropic", "name": "Claude Sonnet 4"},
    ]
