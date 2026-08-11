"""LLM 统一客户端。

对齐 PRD 第 7 节, 实际降级链: OpenClaw → Hermes (启用时) → Kaiweb → OpenAI → Anthropic → dev mock。
通过 httpx 直调 HTTP API, 不引入 langchain/openai SDK。
供应商 API Key 经 llm_config 做 DB 热更新: 先读内存缓存, 缓存为空回落 settings (.env)。
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings
from app.core import llm_config
from app.utils.crypto import decrypt

logger = logging.getLogger("claw.llm")


def _should_try_openclaw(model: str) -> bool:
    """Use OpenClaw for default routing only when chat is configured.

    Explicit OpenClaw model selections still probe the gateway so operators can
    diagnose a newly configured provider without restarting Klaw.
    """
    return settings.openclaw_chat_enabled or model == "openclaw" or model.startswith(
        ("openclaw/", "openclaw:", "agent:")
    )


def _should_try_hermes(model: str) -> bool:
    """Route to Hermes only when configured or explicitly selected."""
    return settings.hermes_chat_enabled or model == "hermes" or model.startswith("hermes/")


def _hermes_model(model: str) -> str:
    if model.startswith("hermes/") and model != "hermes/hermes-agent":
        return model.removeprefix("hermes/")
    return "hermes-agent"


async def _retry_once(call, provider: str):
    """5xx / 连接错误时 0.5s 退避重试一次; 其它错误直接抛出进入降级链。"""
    try:
        return await call()
    except httpx.HTTPStatusError as e:
        if e.response.status_code < 500:
            raise
        logger.warning("%s 调用返回 %s, 0.5s 后重试一次", provider, e.response.status_code)
    except httpx.TransportError as e:
        logger.warning("%s 连接错误 (%s), 0.5s 后重试一次", provider, e)
    await asyncio.sleep(0.5)
    return await call()


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
      1. OpenClaw (本地 agent 网关, settings.openclaw_url) — agent 上下文/工具/供应商路由由 OpenClaw 托管, 数据不出域
      2. Hermes (本地 OpenAI 兼容网关, 显式启用后参与 fallback)
      3. Kaiweb 直连 (自建 OpenAI 兼容网关)
      4. OpenAI (用户 API Key 或全局配置)
      5. Anthropic (全局配置)
      6. dev mock 兜底 (仅 environment=dev)

    供应商 Key 先读 llm_config 内存缓存 (DB 热更新), 缓存为空回落 settings。
    每级 5xx / 连接错误 0.5s 退避重试一次后再降级。

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
    # 1. OpenClaw owns agent context, tools, and provider routing when enabled.
    if _should_try_openclaw(model):
        try:
            result = await _retry_once(
                lambda: _call_openclaw(messages, model, temperature, max_tokens, timeout),
                "OpenClaw",
            )
            if result:
                logger.info("LLM 调用成功: OpenClaw (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("OpenClaw 调用失败, 尝试 fallback: %s", e)

    # 2. Hermes local gateway (disabled until its inference provider is configured).
    if _should_try_hermes(model):
        try:
            result = await _retry_once(
                lambda: _call_openai_compatible(
                    messages,
                    _hermes_model(model),
                    f"{settings.hermes_url.rstrip('/')}/v1",
                    settings.hermes_api_server_key,
                    "hermes",
                    temperature,
                    max_tokens,
                    timeout,
                ),
                "Hermes",
            )
            if result:
                logger.info("LLM 调用成功: Hermes (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("Hermes 调用失败, 尝试 fallback: %s", e)

    # 3. Kaiweb 直连兜底 (Key 经 llm_config 热更新, 缓存为空回落 settings)
    kaiweb_key = llm_config.get_key("kaiweb")
    if kaiweb_key:
        try:
            result = await _retry_once(
                lambda: _call_openai_compatible(
                    messages, _resolve_kaiweb_model(model), settings.kaiweb_base_url, kaiweb_key,
                    "kaiweb", temperature, max_tokens, timeout,
                ),
                "Kaiweb",
            )
            if result:
                logger.info("LLM 调用成功: Kaiweb fallback (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("Kaiweb 调用失败, 尝试 fallback: %s", e)

    # 4. 尝试 OpenAI
    openai_key = _get_openai_key(user)
    if openai_key:
        try:
            result = await _retry_once(
                lambda: _call_openai(messages, model, openai_key, temperature, max_tokens, timeout),
                "OpenAI",
            )
            if result:
                logger.info("LLM 调用成功: OpenAI (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("OpenAI 调用失败, 尝试 fallback: %s", e)

    # 5. 尝试 Anthropic
    anthropic_key = llm_config.get_key("anthropic")
    if anthropic_key:
        try:
            result = await _retry_once(
                lambda: _call_anthropic(messages, model, anthropic_key, temperature, max_tokens, timeout),
                "Anthropic",
            )
            if result:
                logger.info("LLM 调用成功: Anthropic (model=%s)", model)
                return result
        except Exception as e:
            logger.warning("Anthropic 调用失败: %s", e)

    # 6. dev 兜底: 所有真实供应商不可用时, 返回模板化回复 (仅开发环境)
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
    """获取 OpenAI API Key: 优先用户配置, 其次全局 (llm_config 缓存 → settings)。

    用户 Key 解密失败时按未配置处理并记日志, 不把密文当明文 Key 使用。
    """
    if user and user.openai_api_key:
        try:
            return decrypt(user.openai_api_key)
        except Exception:
            logger.warning(
                "用户 OpenAI API Key 解密失败, 按未配置处理 (user_id=%s)",
                getattr(user, "id", None),
            )
    return llm_config.get_key("openai")


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
    api_key = llm_config.get_key("kaiweb")
    if not api_key:
        return False
    try:
        timeout = httpx.Timeout(20.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{settings.kaiweb_base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
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

    优先级: OpenClaw → Hermes → Kaiweb 直连 → OpenAI → 非流式 chat() 一次性 yield。
    已开始输出 (yield) 后失败不再降级 (避免重复内容), 异常向上抛出;
    流式 0 字节视为失败, 继续降级到下一供应商。
    """
    # 1. OpenClaw owns the primary streaming path when chat routing is enabled.
    if _should_try_openclaw(model):
        started = False
        try:
            async for chunk in _stream_openclaw(messages, model, temperature, max_tokens, timeout):
                started = True
                yield chunk
            if started:
                return
            logger.warning("OpenClaw 流式返回 0 字节, 视为失败继续降级")
        except Exception as e:
            if started:
                logger.error("OpenClaw 流式中途失败, 已输出部分内容, 不再降级: %s", e)
                raise
            logger.warning("OpenClaw 流式失败, 尝试 fallback: %s", e)

    # 2. Hermes local gateway streaming.
    if _should_try_hermes(model):
        started = False
        try:
            async for chunk in _stream_openai_compatible(
                messages,
                _hermes_model(model),
                f"{settings.hermes_url.rstrip('/')}/v1",
                settings.hermes_api_server_key,
                "hermes",
                temperature,
                max_tokens,
                timeout,
            ):
                started = True
                yield chunk
            if started:
                return
            logger.warning("Hermes 流式返回 0 字节, 视为失败继续降级")
        except Exception as e:
            if started:
                logger.error("Hermes 流式中途失败, 已输出部分内容, 不再降级: %s", e)
                raise
            logger.warning("Hermes 流式失败, 尝试 fallback: %s", e)

    # 3. Kaiweb 直连流式兜底 (Key 经 llm_config 热更新, 缓存为空回落 settings)
    kaiweb_key = llm_config.get_key("kaiweb")
    if kaiweb_key:
        started = False
        try:
            async for chunk in _stream_openai_compatible(
                messages, _resolve_kaiweb_model(model), settings.kaiweb_base_url, kaiweb_key, "kaiweb",
                temperature, max_tokens, timeout,
            ):
                started = True
                yield chunk
            if started:
                return
            logger.warning("Kaiweb 流式返回 0 字节, 视为失败继续降级")
        except Exception as e:
            if started:
                logger.error("Kaiweb 流式中途失败, 已输出部分内容, 不再降级: %s", e)
                raise
            logger.warning("Kaiweb 流式失败, 尝试 fallback: %s", e)

    # 4. 尝试 OpenAI 流式
    openai_key = _get_openai_key(user)
    if openai_key:
        started = False
        try:
            async for chunk in _stream_openai(messages, model, openai_key, temperature, max_tokens, timeout):
                started = True
                yield chunk
            if started:
                return
            logger.warning("OpenAI 流式返回 0 字节, 视为失败继续降级")
        except Exception as e:
            if started:
                logger.error("OpenAI 流式中途失败, 已输出部分内容, 不再降级: %s", e)
                raise
            logger.warning("OpenAI 流式失败, 尝试非流式: %s", e)

    # 5. 降级: 非流式调用, 一次性 yield
    result = await chat(messages, model=model, user=user, temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    yield result


async def _stream_openclaw(
    messages: list[dict], model: str, temperature: float, max_tokens: int, timeout: float
) -> AsyncGenerator[str, None]:
    """OpenClaw SSE 流式调用 (agent-first 模型契约)。兼容推理模型: delta.content 为空时取 reasoning_content。"""
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
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content") or delta.get("reasoning_content") or ""
                    if text:
                        yield text
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
    """任意 OpenAI 兼容端点的 SSE 流式调用 (OpenAI / Kaiweb / 自建网关)。

    兼容推理模型: delta.content 为空时取 delta.reasoning_content。
    """
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
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    text = delta.get("content") or delta.get("reasoning_content") or ""
                    if text:
                        yield text
                except json.JSONDecodeError:
                    continue


async def list_models() -> list[dict]:
    """列出可用模型。优先 Kaiweb (真实网关), 其次 OpenClaw, 最后预定义列表。"""
    # 1. Kaiweb (配置 Key 时拉取真实模型列表)
    kaiweb_key = llm_config.get_key("kaiweb")
    if kaiweb_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{settings.kaiweb_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {kaiweb_key}"},
                )
                if resp.status_code < 400:
                    data = resp.json()
                    models = data.get("data", [])
                    kaiweb_models = [
                        {"id": m.get("id", ""), "provider": "kaiweb", "name": m.get("id", "")}
                        for m in models
                    ]
                    if kaiweb_models:
                        return _with_hermes_model(kaiweb_models)
        except Exception as e:
            logger.warning("Kaiweb 模型列表拉取失败: %s", e)

    # 2. OpenClaw. A healthy tools-only gateway must not advertise models.
    if settings.openclaw_chat_enabled:
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
                        return _with_hermes_model(openclaw_models)
        except Exception as e:
            logger.warning("OpenClaw 模型列表拉取失败: %s", e)

    # 3. Config-derived fallback list. Do not advertise providers with no key.
    configured_models = [
        {"id": "default", "provider": "auto", "name": "默认路由"},
    ]
    if kaiweb_key:
        configured_models.append(
            {"id": settings.kaiweb_model, "provider": "kaiweb", "name": settings.kaiweb_model}
        )
    if llm_config.get_key("openai"):
        configured_models.append(
            {"id": "gpt-4o-mini", "provider": "openai", "name": "GPT-4o mini"}
        )
    if llm_config.get_key("anthropic"):
        configured_models.append(
            {
                "id": "claude-sonnet-4-20250514",
                "provider": "anthropic",
                "name": "Claude Sonnet 4",
            }
        )
    if settings.environment == "dev":
        configured_models.append(
            {"id": "mock", "provider": "mock", "name": "Mock (开发兜底)"}
        )
    return _with_hermes_model(configured_models)


def _with_hermes_model(models: list[dict]) -> list[dict]:
    """Expose Hermes only after operators enable its inference routing."""
    if not settings.hermes_chat_enabled:
        return models
    if any(model.get("provider") == "hermes" for model in models):
        return models
    return [
        *models,
        {"id": "hermes/hermes-agent", "provider": "hermes", "name": "Hermes Agent"},
    ]
