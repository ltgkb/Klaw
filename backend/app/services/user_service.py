"""用户业务逻辑。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import UserLogin, UserRegister
from app.schemas.user import UserUpdate
from app.utils.crypto import encrypt


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    """注册新用户。首个用户自动成为 admin。"""
    # 检查邮箱是否已注册
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("该邮箱已注册")

    # 判断是否为首个用户
    count_result = await db.execute(select(User))
    is_first = count_result.scalars().first() is None

    user = User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
        role=UserRole.admin if is_first else UserRole.user,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # 并发注册竞态：邮箱唯一约束兜底，转 409
        await db.rollback()
        raise ValueError("该邮箱已注册") from None
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, data: UserLogin) -> User | None:
    """校验邮箱+密码，返回用户或 None。"""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(data.password, user.hashed_password):
        return None
    return user


def issue_tokens(user: User) -> tuple[str, str]:
    """为用户签发 access + refresh token。"""
    access = create_access_token(
        subject=str(user.id),
        extra={"role": user.role.value, "email": user.email},
    )
    refresh = create_refresh_token(subject=str(user.id))
    return access, refresh


async def update_user(db: AsyncSession, user: User, data: UserUpdate) -> User:
    """更新用户信息。API Key 加密后存储。

    openai_api_key: 传非空字符串 → 加密存储; 传空字符串 "" → 清除; None → 不变。
    """
    if data.name is not None:
        user.name = data.name
    if data.openai_api_key is not None:
        user.openai_api_key = encrypt(data.openai_api_key) if data.openai_api_key.strip() else None
    if data.openclaw_config is not None:
        user.openclaw_config = data.openclaw_config
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())
