"""认证端点：注册/登录/刷新token/当前用户。对齐 PRD 6.x。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DBSession
from app.core.security import decode_token
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenResponse, UserLogin, UserRegister
from app.schemas.user import UserRead
from app.services.user_service import authenticate_user, issue_tokens, register_user

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: UserRegister, db: DBSession):
    """用户注册。首个用户自动成为 admin。"""
    try:
        user = await register_user(db, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return UserRead.model_validate(user).model_copy(update={"has_openai_key": user.openai_api_key is not None})


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: DBSession):
    """用户登录，返回 JWT。OAuth2 password flow。"""
    user = await authenticate_user(db, data)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access, refresh = issue_tokens(user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: DBSession):
    """用 refresh token 换取新的 access token。"""
    payload = decode_token(data.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 refresh token")

    # 畸形 sub（缺失或非合法 UUID）按未认证处理，不抛 500
    sub = payload.get("sub")
    try:
        user_uuid = uuid.UUID(sub)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 refresh token"
        ) from None

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    access, new_refresh = issue_tokens(user)
    return TokenResponse(access_token=access, refresh_token=new_refresh)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser):
    """获取当前登录用户信息。"""
    return UserRead.model_validate(current_user).model_copy(
        update={"has_openai_key": current_user.openai_api_key is not None}
    )
