"""系统配置端点 (embedding / LLM 模型 API 等)。读取需登录, 修改需 admin。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, require_roles
from app.core import embedding_config, llm_config, tei_client
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.schemas.system import EmbeddingConfigRead, EmbeddingConfigUpdate, LlmConfigRead, LlmConfigUpdate
from app.core.database import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/system", tags=["系统配置"])

AdminUser = Annotated[User, Depends(require_roles("admin"))]

LLM_DEFAULT_MODEL_KEY = "llm.default_model"


async def _get_setting(db: AsyncSession, key: str) -> str:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else ""


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        db.add(SystemSetting(key=key, value=value))
    else:
        row.value = value
    await db.commit()


async def _read() -> EmbeddingConfigRead:
    cfg = embedding_config.get()
    configured = bool(cfg["base_url"] and cfg["api_key"])
    if configured:
        source = "api"
    else:
        tei_ok = await tei_client.health_check()
        source = "tei" if tei_ok else "hash"
    return EmbeddingConfigRead(
        base_url=cfg["base_url"],
        model=cfg["model"],
        has_key=bool(cfg["api_key"]),
        configured=configured,
        source=source,
    )


async def _llm_read(db: AsyncSession) -> LlmConfigRead:
    key_status = llm_config.status()
    return LlmConfigRead(
        default_model=await _get_setting(db, LLM_DEFAULT_MODEL_KEY),
        has_kaiweb_key=key_status["kaiweb"],
        has_openai_key=key_status["openai"],
        has_anthropic_key=key_status["anthropic"],
    )


@router.get("/embedding-config", response_model=EmbeddingConfigRead)
async def get_embedding_config(_: CurrentUser):
    """读取 embedding 模型 API 配置。"""
    return await _read()


@router.put("/embedding-config", response_model=EmbeddingConfigRead)
async def update_embedding_config(
    _: AdminUser,
    data: EmbeddingConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新 embedding 模型 API 配置 (base_url / api_key / model)。api_key 加密存储。

    api_key 为空时保留已有 Key (不清除), 便于只改 base_url/model;
    clear_key=true 时显式清除已保存的 Key。
    """
    if data.clear_key:
        api_key = ""
    elif data.api_key:
        api_key = data.api_key
    else:
        # 保留已有 Key
        api_key = embedding_config.get().get("api_key", "")
    await embedding_config.save(db, data.base_url, api_key, data.model)
    return await _read()


@router.get("/llm-config", response_model=LlmConfigRead)
async def get_llm_config(_: CurrentUser, db: AsyncSession = Depends(get_db)):
    """读取 LLM 配置 (默认模型 + 各供应商 Key 是否已配置, key 脱敏)。"""
    return await _llm_read(db)


@router.put("/llm-config", response_model=LlmConfigRead)
async def set_llm_config(
    _: AdminUser,
    data: LlmConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """设置 LLM 默认模型与供应商 API Key (DB 持久化 + 内存热更新, Key 加密存储)。

    各 api_key 为空时保留已有 Key (不清除), 便于只改默认模型或单个 Key。
    """
    cached = llm_config.get_cached()
    await llm_config.save(
        db,
        kaiweb_api_key=data.kaiweb_api_key or cached.get("kaiweb", ""),
        openai_api_key=data.openai_api_key or cached.get("openai", ""),
        anthropic_api_key=data.anthropic_api_key or cached.get("anthropic", ""),
    )
    await _set_setting(db, LLM_DEFAULT_MODEL_KEY, data.default_model)
    return await _llm_read(db)
