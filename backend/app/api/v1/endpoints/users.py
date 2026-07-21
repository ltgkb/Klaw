"""用户管理端点 (admin only)。对齐 PRD RBAC 要求。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, DBSession, require_roles
from app.models.user import User, UserRole
from app.schemas.user import UserRead, UserUpdate
from app.services.user_service import list_users, update_user

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", response_model=list[UserRead])
async def get_users(
    db: DBSession,
    _: User = Depends(require_roles("admin")),
):
    """获取用户列表 (仅 admin)。"""
    users = await list_users(db)
    return [
        UserRead.model_validate(u).model_copy(update={"has_openai_key": u.openai_api_key is not None})
        for u in users
    ]


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: uuid.UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """获取指定用户详情。用户可查自己，admin 可查任意。"""
    if current_user.role != UserRole.admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权查看其他用户")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return UserRead.model_validate(user).model_copy(update={"has_openai_key": user.openai_api_key is not None})


@router.put("/me", response_model=UserRead)
async def update_me(
    data: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """更新当前用户信息。"""
    user = await update_user(db, current_user, data)
    return UserRead.model_validate(user).model_copy(update={"has_openai_key": user.openai_api_key is not None})


@router.put("/{user_id}/role", response_model=UserRead)
async def update_user_role(
    user_id: uuid.UUID,
    role: UserRole,
    db: DBSession,
    _: User = Depends(require_roles("admin")),
):
    """修改用户角色 (仅 admin)。"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    # 保护最后一个 admin：不允许将其降级，否则系统将无管理员
    if user.role == UserRole.admin and role != UserRole.admin:
        admin_count = (
            await db.execute(
                select(func.count()).select_from(User).where(User.role == UserRole.admin)
            )
        ).scalar_one()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能降级最后一个 admin，请先指定其他 admin",
            )
    user.role = role
    await db.commit()
    await db.refresh(user)
    return UserRead.model_validate(user).model_copy(update={"has_openai_key": user.openai_api_key is not None})
