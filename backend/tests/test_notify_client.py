"""WP2 推送 SSRF 防护与误判修复测试。

覆盖:
- 四渠道 payload 结构与显式成功判定 (飞书/企微/Telegram)
- Telegram Markdown 400 → 降级纯文本重发
- notify() 分发前 SSRF 拦截 (非公网地址 / 非法 scheme / 非法 bot_token)
- 创建渠道按类型校验必填字段 (422) 与 host 白名单 (prod 拒绝, dev 放行)
- 仅敏感字段加密存储, chat_id 明文回显
- 解密失败的渠道被跳过, 不当明文发送
"""

import uuid

import pytest

from app.core import notify_client
from app.core.notify_client import notify, send_feishu, send_telegram, send_wechat


# ── httpx Mock 工具 ──

class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = b"x"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    """仿 httpx.AsyncClient, 按 responder(url, json) 生成响应并记录请求。"""

    def __init__(self, responder, requests):
        self._responder = responder
        self._requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, **kwargs):
        self._requests.append({"url": url, "json": json})
        return self._responder(url, json)


def _patch_httpx(monkeypatch, responder):
    """Patch notify_client.httpx.AsyncClient, 返回请求记录列表。"""
    requests = []

    def factory(*args, **kwargs):
        return _FakeAsyncClient(responder, requests)

    monkeypatch.setattr(notify_client.httpx, "AsyncClient", factory)
    return requests


def _noop_ssrf(monkeypatch):
    """绕过 notify() 内的 SSRF DNS 校验 (payload/判定类测试用)。"""
    monkeypatch.setattr(notify_client, "assert_url_is_safe", lambda url: ("host", "1.1.1.1"))


# ── 飞书 payload 与成功判定 ──

@pytest.mark.asyncio
async def test_feishu_payload_and_success(monkeypatch):
    requests = _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"code": 0}))
    ok = await send_feishu("https://open.feishu.cn/hook/x", "标题", "内容")
    assert ok is True
    payload = requests[0]["json"]
    assert payload["msg_type"] == "interactive"
    assert payload["card"]["header"]["title"]["content"] == "标题"


@pytest.mark.asyncio
async def test_feishu_status_code_variant(monkeypatch):
    _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"StatusCode": 0}))
    assert await send_feishu("https://open.feishu.cn/hook/x", "t", "c") is True


@pytest.mark.asyncio
async def test_feishu_missing_code_not_misjudged(monkeypatch):
    """响应缺少 code/StatusCode 字段时不得误判成功。"""
    _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"msg": "weird"}))
    assert await send_feishu("https://open.feishu.cn/hook/x", "t", "c") is False


@pytest.mark.asyncio
async def test_feishu_nonzero_code_fails(monkeypatch):
    _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"code": 9499}))
    assert await send_feishu("https://open.feishu.cn/hook/x", "t", "c") is False


# ── 企业微信 payload 与成功判定 ──

@pytest.mark.asyncio
async def test_wechat_payload_and_success(monkeypatch):
    requests = _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"errcode": 0}))
    ok = await send_wechat("https://qyapi.weixin.qq.com/hook/x", "标题", "内容")
    assert ok is True
    payload = requests[0]["json"]
    assert payload["msgtype"] == "markdown"
    assert "标题" in payload["markdown"]["content"]


@pytest.mark.asyncio
async def test_wechat_missing_errcode_not_misjudged(monkeypatch):
    """响应缺少 errcode 字段时不得误判成功。"""
    _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"errmsg": "ok-ish"}))
    assert await send_wechat("https://qyapi.weixin.qq.com/hook/x", "t", "c") is False


# ── Telegram: Markdown 降级 + 成功判定 ──

@pytest.mark.asyncio
async def test_telegram_success(monkeypatch):
    requests = _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"ok": True}))
    ok = await send_telegram("123456:ABC-def_ghi", "123", "*标题*")
    assert ok is True
    assert requests[0]["json"]["parse_mode"] == "Markdown"
    assert "bot123456:ABC-def_ghi" in requests[0]["url"]


@pytest.mark.asyncio
async def test_telegram_markdown_fallback_to_plain(monkeypatch):
    """Markdown 解析失败 (400) 时降级纯文本重发一次。"""
    calls = []

    def responder(url, json):
        calls.append(json)
        if json.get("parse_mode") == "Markdown":
            return _FakeResponse(400, {"ok": False, "description": "Bad Request: can't parse entities"})
        return _FakeResponse(200, {"ok": True})

    _patch_httpx(monkeypatch, responder)
    ok = await send_telegram("123456:ABC-def_ghi", "123", "*坏markdown")
    assert ok is True
    assert len(calls) == 2
    assert "parse_mode" not in calls[1]


@pytest.mark.asyncio
async def test_telegram_fallback_also_fails(monkeypatch):
    _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(400, {"ok": False}))
    assert await send_telegram("123456:ABC-def_ghi", "123", "x") is False


@pytest.mark.asyncio
async def test_telegram_invalid_token_rejected(monkeypatch):
    requests = _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"ok": True}))
    with pytest.raises(ValueError, match="bot_token"):
        await send_telegram("bad/token?x=1", "123", "hi")
    assert requests == []  # 未发出任何请求


# ── notify() 分发前 SSRF 拦截 ──

@pytest.mark.asyncio
async def test_notify_ssrf_blocks_private_ip(monkeypatch):
    """非公网地址在分发前被 SSRF 防护拦截, 不发出 HTTP 请求。"""
    requests = _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"code": 0}))
    results = await notify(
        [{"type": "feishu", "webhook_url": "http://127.0.0.1:9000/hook"}], "t", "c"
    )
    assert results[0]["success"] is False
    assert "安全校验" in results[0]["error"]
    assert requests == []


@pytest.mark.asyncio
async def test_notify_ssrf_blocks_bad_scheme(monkeypatch):
    requests = _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"code": 0}))
    results = await notify(
        [{"type": "wechat", "webhook_url": "file:///etc/passwd"}], "t", "c"
    )
    assert results[0]["success"] is False
    assert requests == []


@pytest.mark.asyncio
async def test_notify_dispatch_success(monkeypatch):
    """合法公网 webhook 正常分发 (SSRF 校验打桩)。"""
    _noop_ssrf(monkeypatch)
    _patch_httpx(monkeypatch, lambda url, json: _FakeResponse(200, {"code": 0}))
    results = await notify(
        [{"type": "feishu", "webhook_url": "https://open.feishu.cn/hook/x"}], "t", "c"
    )
    assert results == [{"channel": "feishu", "success": True, "error": None}]


@pytest.mark.asyncio
async def test_notify_unknown_type(monkeypatch):
    results = await notify([{"type": "sms"}], "t", "c")
    assert results[0]["success"] is False
    assert "未知渠道类型" in results[0]["error"]


# ── Schema: 按类型校验必填字段 → 422 ──

def test_schema_required_fields_by_type():
    from pydantic import ValidationError

    from app.schemas.push_channel import PushChannelCreate

    with pytest.raises(ValidationError):
        PushChannelCreate(name="x", type="telegram", config={"bot_token": "1:a"})
    with pytest.raises(ValidationError):
        PushChannelCreate(name="x", type="feishu", config={})
    with pytest.raises(ValidationError):
        PushChannelCreate(name="x", type="hermes", config={})
    # 合法配置通过
    ok = PushChannelCreate(
        name="x", type="telegram", config={"bot_token": "1:a", "chat_id": "9"}
    )
    assert ok.type.value == "telegram"


# ── 端点: 创建校验 / 明文回显 / 白名单 / 解密失败跳过 ──

async def _register_and_login(client, email):
    """注册并登录, 返回认证头。"""
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "WP2 Tester", "password": "pass1234",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": "pass1234",
    })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_create_channel_missing_fields_422(client):
    h = await _register_and_login(client, "wp2-422@test.com")
    resp = await client.post("/api/v1/push/channels", json={
        "name": "tg", "type": "telegram", "config": {"bot_token": "1:a"},
    }, headers=h)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_channel_plaintext_chat_id_echo(client):
    """chat_id 明文存储并明文回显, bot_token 加密存储并脱敏。"""
    h = await _register_and_login(client, "wp2-echo@test.com")
    resp = await client.post("/api/v1/push/channels", json={
        "name": "tg", "type": "telegram",
        "config": {"bot_token": "123:abc", "chat_id": "123456"},
    }, headers=h)
    assert resp.status_code == 201
    cfg = resp.json()["config"]
    assert cfg["bot_token"] == "******"
    assert cfg["chat_id"] == "123456"

    # 通过列表接口再确认明文回显一致
    resp = await client.get("/api/v1/push/channels", headers=h)
    assert resp.json()[0]["config"]["chat_id"] == "123456"


@pytest.mark.asyncio
async def test_create_channel_host_whitelist_prod_rejects(client, monkeypatch):
    """prod 环境下非白名单 host 创建飞书渠道被拒绝。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "environment", "prod")
    h = await _register_and_login(client, "wp2-wl@test.com")
    resp = await client.post("/api/v1/push/channels", json={
        "name": "fs", "type": "feishu",
        "config": {"webhook_url": "https://evil.example.com/hook"},
    }, headers=h)
    assert resp.status_code == 400

    # 白名单内 host 放行
    resp = await client.post("/api/v1/push/channels", json={
        "name": "fs", "type": "feishu",
        "config": {"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/x"},
    }, headers=h)
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_notify_skips_channel_on_decrypt_failure(client, db_session, monkeypatch):
    """已持久化渠道敏感字段解密失败 → 记 warning 跳过该渠道, 不当明文发送。"""
    from app.models.push_channel import ChannelType, PushChannel

    sent = []

    async def mock_notify(channels, title, content):
        sent.extend(channels)
        return [{"channel": c.get("type", ""), "success": True, "error": None} for c in channels]

    from app.api.v1.endpoints import notifications as notif_ep
    monkeypatch.setattr(notif_ep, "notify", mock_notify)

    h = await _register_and_login(client, "wp2-dec@test.com")

    # 先创建一个正常渠道拿 owner_id
    resp = await client.post("/api/v1/push/channels", json={
        "name": "tg", "type": "telegram",
        "config": {"bot_token": "123:abc", "chat_id": "999"},
    }, headers=h)
    good_id = resp.json()["id"]

    # 直接写库一个密文损坏的渠道 (同一 owner)
    from sqlalchemy import select

    from app.models.user import User
    result = await db_session.execute(select(User).where(User.email == "wp2-dec@test.com"))
    owner = result.scalar_one()
    broken = PushChannel(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name="broken",
        type=ChannelType.telegram,
        config={"bot_token": "!!!not-valid-ciphertext!!!", "chat_id": "111"},
    )
    db_session.add(broken)
    await db_session.commit()

    # 只引用损坏渠道 → 全部被跳过 → 400
    resp = await client.post("/api/v1/notifications/send", json={
        "title": "t", "content": "c", "channel_ids": [str(broken.id)],
    }, headers=h)
    assert resp.status_code == 400

    # 损坏 + 正常渠道 → 仅正常渠道参与推送, 密文不外泄
    resp = await client.post("/api/v1/notifications/send", json={
        "title": "t", "content": "c", "channel_ids": [str(broken.id), good_id],
    }, headers=h)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1
    assert len(sent) == 1
    assert sent[0]["bot_token"] == "123:abc"  # 正常渠道已正确解密
    assert "!!!not-valid-ciphertext!!!" not in str(sent)
