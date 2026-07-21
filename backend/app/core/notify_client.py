"""多平台推送客户端。对齐 PRD M4。

支持: 飞书 / 企业微信 / Telegram (httpx 直调 Webhook) + Hermes (可选)。
用户可控的外发 URL 在分发前统一过 SSRF 校验 (common.ssrf_guard)。
"""

import logging
import re

import httpx

from app.core.config import settings
from common.ssrf_guard import assert_url_is_safe

logger = logging.getLogger("claw.notify")

# Telegram Bot Token 格式 (token 嵌入请求 URL 路径, 需防注入)
_TELEGRAM_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]+$")


async def send_feishu(webhook_url: str, title: str, content: str) -> bool:
    """飞书机器人 Webhook 推送 (交互式卡片)。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json={
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": content}],
            },
        })
        if resp.status_code >= 400:
            raise RuntimeError(f"飞书 Webhook HTTP {resp.status_code}")
        data = resp.json()
        # 显式存在性判断: code / StatusCode 都缺失时不得误判成功
        if "code" in data:
            success = data["code"] == 0
        elif "StatusCode" in data:
            success = data["StatusCode"] == 0
        else:
            success = False
        if not success:
            logger.warning("飞书拒绝推送: code=%s", data.get("code", data.get("StatusCode")))
        return success


async def send_wechat(webhook_url: str, title: str, content: str) -> bool:
    """企业微信机器人 Webhook 推送 (Markdown)。"""
    text = f"## {title}\n\n{content}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json={
            "msgtype": "markdown",
            "markdown": {"content": text},
        })
        if resp.status_code >= 400:
            raise RuntimeError(f"企业微信 Webhook HTTP {resp.status_code}")
        data = resp.json()
        # 显式存在性判断: 缺少 errcode 字段视为失败
        success = "errcode" in data and data["errcode"] == 0
        if not success:
            logger.warning("企业微信拒绝推送: errcode=%s", data.get("errcode"))
        return success


async def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """Telegram Bot API 推送 (Markdown 失败时降级纯文本重发一次)。"""
    if not _TELEGRAM_TOKEN_RE.match(bot_token):
        raise ValueError("Telegram bot_token 格式非法")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        })
        try:
            data = resp.json()
        except Exception:
            data = {}
        if resp.status_code == 200:
            return "ok" in data and data["ok"] is True
        # Markdown 解析失败 (HTTP 400) → 去掉 parse_mode 降级纯文本重发
        if resp.status_code == 400:
            logger.warning(
                "Telegram Markdown 发送失败, 降级纯文本重发: %s", data.get("description")
            )
            resp2 = await client.post(url, json={"chat_id": chat_id, "text": text})
            try:
                data2 = resp2.json()
            except Exception:
                data2 = {}
            if resp2.status_code != 200:
                logger.warning("Telegram 纯文本重发仍失败: HTTP %s", resp2.status_code)
                return False
            return "ok" in data2 and data2["ok"] is True
        resp.raise_for_status()
        return False


async def send_hermes(channel: str, message: str) -> bool:
    """通过 Hermes gateway 推送 (HTTP API, 若可用)。

    Hermes 默认不暴露 HTTP API, 此方法为可选通道。
    """
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(
            f"{settings.hermes_url}/api/send",
            json={"channel": channel, "message": message},
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Hermes API HTTP {resp.status_code}")
        return True


async def notify(channels: list[dict], title: str, content: str) -> list[dict]:
    """统一推送入口: 根据渠道配置分发。

    用户提供的 webhook_url 在分发前经 SSRF 校验 (非公网地址直接拦截)。

    Args:
        channels: 渠道配置列表, 每项含 type + 渠道参数
        title: 推送标题
        content: 推送内容

    Returns:
        每个渠道的推送结果 [{channel, success, error}]
    """
    results = []
    for ch in channels:
        ch_type = ch.get("type", "")
        success = False
        error = None
        try:
            if ch_type == "feishu":
                assert_url_is_safe(ch["webhook_url"])
                success = await send_feishu(ch["webhook_url"], title, content)
            elif ch_type == "wechat":
                assert_url_is_safe(ch["webhook_url"])
                success = await send_wechat(ch["webhook_url"], title, content)
            elif ch_type == "telegram":
                full_text = f"*{title}*\n\n{content}"
                success = await send_telegram(ch["bot_token"], ch["chat_id"], full_text)
            elif ch_type == "hermes":
                success = await send_hermes(ch.get("channel", ""), f"{title}\n{content}")
            else:
                error = f"未知渠道类型: {ch_type}"
        except ValueError as e:
            error = f"渠道配置/URL 安全校验失败: {e}"
            logger.warning("推送被安全校验拦截: %s — %s", ch_type, e)
        except Exception as e:
            error = str(e)

        if not success and error is None:
            error = "渠道返回失败状态"

        results.append({"channel": ch_type, "success": success, "error": error})
        if success:
            logger.info("推送成功: %s", ch_type)
        else:
            logger.warning("推送失败: %s — %s", ch_type, error)

    return results
