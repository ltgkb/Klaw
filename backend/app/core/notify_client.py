"""多平台推送客户端。对齐 PRD M4。

支持: 飞书 / 企业微信 / Telegram (httpx 直调 Webhook) + Hermes (可选)。
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("claw.notify")


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
        if "code" in data:
            success = data["code"] == 0
        elif "StatusCode" in data:
            success = data["StatusCode"] == 0
        else:
            success = False
        if not success:
            raise RuntimeError(f"飞书拒绝推送: code={data.get('code', data.get('StatusCode'))}")
        return True


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
        if data.get("errcode") != 0:
            raise RuntimeError(f"企业微信拒绝推送: errcode={data.get('errcode')}")
        return True


async def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    """Telegram Bot API 推送。"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        })
        if resp.status_code >= 400:
            raise RuntimeError(f"Telegram API HTTP {resp.status_code}")
        data = resp.json()
        if not data.get("ok", False):
            raise RuntimeError("Telegram API 返回失败")
        return True


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
                success = await send_feishu(ch["webhook_url"], title, content)
            elif ch_type == "wechat":
                success = await send_wechat(ch["webhook_url"], title, content)
            elif ch_type == "telegram":
                full_text = f"*{title}*\n\n{content}"
                success = await send_telegram(ch["bot_token"], ch["chat_id"], full_text)
            elif ch_type == "hermes":
                success = await send_hermes(ch.get("channel", ""), f"{title}\n{content}")
            else:
                error = f"未知渠道类型: {ch_type}"
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
