"""LLM 供应商 API Key 配置 (内存缓存 + DB 持久化)。

仿 embedding_config: Key 存 system_settings 表 (键 llm.*, 加密存储),
管理员通过 PUT /system/llm-config 修改后即时生效 (热更新);
llm_client.chat()/chat_stream() 先读内存缓存, 缓存为空回落 settings (.env)。
"""

import threading

from app.core.config import settings

# 内存缓存 (api_key 明文, 仅进程内)
_cache: dict[str, str] = {"kaiweb": "", "openai": "", "anthropic": ""}
_lock = threading.Lock()

KEY_KAIWEB = "llm.kaiweb_api_key"  # 加密存储
KEY_OPENAI = "llm.openai_api_key"  # 加密存储
KEY_ANTHROPIC = "llm.anthropic_api_key"  # 加密存储

_PROVIDERS = ("kaiweb", "openai", "anthropic")


def get_cached() -> dict[str, str]:
    """返回当前内存缓存的原始值 (不含 settings 回落)。"""
    with _lock:
        return dict(_cache)


def get_key(provider: str) -> str:
    """返回指定供应商 API Key: 内存缓存 (DB 热更新) 优先, 回落 settings (.env)。"""
    with _lock:
        cached = _cache.get(provider, "")
    if cached:
        return cached
    return getattr(settings, f"{provider}_api_key", "") or ""


def status() -> dict[str, bool]:
    """各供应商 Key 是否已配置 (缓存或 settings)。"""
    return {p: bool(get_key(p)) for p in _PROVIDERS}


async def load_from_db(db) -> None:
    """启动时从 DB 载入 LLM Key; DB 无则保持空缓存, 由 settings (.env) 兜底。"""
    from sqlalchemy import select
    from app.models.system_setting import SystemSetting
    from app.utils.crypto import decrypt

    result = await db.execute(
        select(SystemSetting).where(
            SystemSetting.key.in_([KEY_KAIWEB, KEY_OPENAI, KEY_ANTHROPIC])
        )
    )
    rows = {r.key: r.value for r in result.scalars().all()}

    loaded: dict[str, str] = {}
    for provider, key in (
        ("kaiweb", KEY_KAIWEB),
        ("openai", KEY_OPENAI),
        ("anthropic", KEY_ANTHROPIC),
    ):
        value = ""
        if rows.get(key):
            try:
                value = decrypt(rows[key])
            except Exception:
                value = rows[key]
        loaded[provider] = value

    with _lock:
        _cache.update(loaded)


async def save(db, kaiweb_api_key: str, openai_api_key: str, anthropic_api_key: str) -> None:
    """持久化 LLM Key 到 DB 并更新内存缓存。Key 加密存储; 空字符串表示清除。"""
    from sqlalchemy import select
    from app.models.system_setting import SystemSetting
    from app.utils.crypto import encrypt

    kv = {
        KEY_KAIWEB: encrypt(kaiweb_api_key) if kaiweb_api_key else "",
        KEY_OPENAI: encrypt(openai_api_key) if openai_api_key else "",
        KEY_ANTHROPIC: encrypt(anthropic_api_key) if anthropic_api_key else "",
    }
    for k, v in kv.items():
        result = await db.execute(select(SystemSetting).where(SystemSetting.key == k))
        row = result.scalar_one_or_none()
        if row is None:
            db.add(SystemSetting(key=k, value=v))
        else:
            row.value = v
    await db.commit()

    with _lock:
        _cache["kaiweb"] = kaiweb_api_key or ""
        _cache["openai"] = openai_api_key or ""
        _cache["anthropic"] = anthropic_api_key or ""
