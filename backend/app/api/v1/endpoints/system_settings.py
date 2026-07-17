"""系统配置端点 (embedding 模型 API 等)。所有登录用户可配置。"""

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser
from app.core import embedding_config, tei_client
from app.models.system_setting import SystemSetting
from app.schemas.system import EmbeddingConfigRead, EmbeddingConfigUpdate, LlmConfigRead, LlmConfigUpdate
from app.core.database import get_db
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/system", tags=["系统配置"])

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


@router.get("/embedding-config", response_model=EmbeddingConfigRead)
async def get_embedding_config(_: CurrentUser):
    """读取 embedding 模型 API 配置。"""
    return await _read()


@router.put("/embedding-config", response_model=EmbeddingConfigRead)
async def update_embedding_config(
    _: CurrentUser,
    data: EmbeddingConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新 embedding 模型 API 配置 (base_url / api_key / model)。api_key 加密存储。

    api_key 为空时保留已有 Key (不清除), 便于只改 base_url/model。
    """
    api_key = data.api_key
    if not api_key:
        # 保留已有 Key
        api_key = embedding_config.get().get("api_key", "")
    await embedding_config.save(db, data.base_url, api_key, data.model)
    return await _read()


@router.get("/llm-config", response_model=LlmConfigRead)
async def get_llm_config(_: CurrentUser, db: AsyncSession = Depends(get_db)):
    """读取 LLM 默认模型 (画布新建 LLM 节点的默认模型)。"""
    return LlmConfigRead(default_model=await _get_setting(db, LLM_DEFAULT_MODEL_KEY))


@router.put("/llm-config", response_model=LlmConfigRead)
async def set_llm_config(
    _: CurrentUser,
    data: LlmConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """设置 LLM 默认模型。"""
    await _set_setting(db, LLM_DEFAULT_MODEL_KEY, data.default_model)
    return LlmConfigRead(default_model=data.default_model)
