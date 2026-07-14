"""用户相关 Pydantic 模型。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class UserRead(BaseModel):
    """用户信息响应 (不含密码)。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # 不返回 openai_api_key 明文，仅标记是否已配置
    has_openai_key: bool = False


class UserUpdate(BaseModel):
    """用户信息更新。"""
    name: str | None = Field(None, min_length=1, max_length=100)
    openai_api_key: str | None = None
    openclaw_config: dict | None = None
