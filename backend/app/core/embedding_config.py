"""Embedding 模型 API 配置 (内存缓存 + DB 持久化)。

优先级 (向量化时): embedding API (本配置) → TEI sidecar → dev 哈希兜底。
配置来自 system_settings 表 (键 embedding.*), 启动时载入内存; 管理员通过 API 修改后即时生效。
"""

import threading

from app.core.config import settings

# 内存缓存 (api_key 明文, 仅进程内)
_cache: dict[str, str] = {"base_url": "", "api_key": "", "model": ""}
_lock = threading.Lock()

KEY_BASE_URL = "embedding.api_base_url"
KEY_API_KEY = "embedding.api_key"  # 加密存储
KEY_MODEL = "embedding.api_model"


def get() -> dict[str, str]:
    """返回当前 embedding API 配置 (内存)。"""
    with _lock:
        return dict(_cache)


def is_configured() -> bool:
    c = get()
    return bool(c["base_url"] and c["api_key"])


async def load_from_db(db) -> None:
    """启动时从 DB 载入 embedding 配置; DB 无则回落到 .env 默认。"""
    from sqlalchemy import select
    from app.models.system_setting import SystemSetting
    from app.utils.crypto import decrypt

    result = await db.execute(
        select(SystemSetting).where(
            SystemSetting.key.in_([KEY_BASE_URL, KEY_API_KEY, KEY_MODEL])
        )
    )
    rows = {r.key: r.value for r in result.scalars().all()}

    base_url = rows.get(KEY_BASE_URL) or settings.embedding_api_base_url
    model = rows.get(KEY_MODEL) or settings.embedding_api_model
    api_key = ""
    if rows.get(KEY_API_KEY):
        try:
            api_key = decrypt(rows[KEY_API_KEY])
        except Exception:
            api_key = rows[KEY_API_KEY]
    elif settings.embedding_api_key:
        api_key = settings.embedding_api_key

    with _lock:
        _cache["base_url"] = base_url or ""
        _cache["api_key"] = api_key or ""
        _cache["model"] = model or ""


async def save(db, base_url: str, api_key: str, model: str) -> None:
    """持久化 embedding 配置到 DB 并更新内存缓存。api_key 加密存储。"""
    from sqlalchemy import select
    from app.models.system_setting import SystemSetting
    from app.utils.crypto import encrypt

    kv = {
        KEY_BASE_URL: base_url or "",
        KEY_MODEL: model or "",
        KEY_API_KEY: encrypt(api_key) if api_key else "",  # 空字符串表示清除
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
        _cache["base_url"] = base_url or ""
        _cache["api_key"] = api_key or ""
        _cache["model"] = model or ""
