"""用户业务逻辑。"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.models.user import User, UserRole
from app.models.refresh_token import RefreshToken
from app.schemas.auth import UserLogin, UserRegister
from app.schemas.user import UserUpdate
from app.utils.crypto import encrypt

_USER_REGISTRATION_LOCK_ID = 1263292791


async def _lock_user_registration(db: AsyncSession) -> None:
    """Serialize first-user role selection on PostgreSQL."""
    bind = db.get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", None)
    if dialect_name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _USER_REGISTRATION_LOCK_ID},
        )


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    """注册新用户。首个用户自动成为 admin。"""
    await _lock_user_registration(db)

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
    # Existing raw-bcrypt hashes remain readable. Passwords within bcrypt's
    # original byte limit can be upgraded without preserving truncation risk.
    if password_needs_rehash(user.hashed_password) and len(data.password.encode("utf-8")) <= 72:
        user.hashed_password = hash_password(data.password)
        await db.commit()
        await db.refresh(user)
    return user


def _refresh_hash(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def _new_refresh_token(user: User) -> tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    return create_refresh_token(subject=str(user.id), jti=jti), _refresh_hash(jti), expires_at


def _access_token(user: User) -> str:
    return create_access_token(
        subject=str(user.id),
        extra={"role": user.role.value, "email": user.email},
    )


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    """Issue an access token and register a one-time refresh token."""
    now = datetime.now(UTC)
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.expires_at < now,
        )
    )
    refresh, token_hash, expires_at = _new_refresh_token(user)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    await db.commit()
    return _access_token(user), refresh


async def rotate_refresh_token(
    db: AsyncSession, user: User, jti: str
) -> tuple[str, str] | None:
    """Atomically consume a refresh token and replace it with a new one."""
    token_hash = _refresh_hash(jti)
    result = await db.execute(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user.id,
            RefreshToken.token_hash == token_hash,
        )
        .with_for_update()
    )
    current = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if current is None or current.revoked_at is not None:
        return None
    expires_at = current.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        current.revoked_at = now
        await db.commit()
        return None

    refresh, replacement_hash, replacement_expires_at = _new_refresh_token(user)
    current.revoked_at = now
    current.replaced_by_hash = replacement_hash
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=replacement_hash,
            expires_at=replacement_expires_at,
        )
    )
    await db.commit()
    return _access_token(user), refresh


async def revoke_refresh_token(db: AsyncSession, user_id, jti: str) -> None:
    """Revoke one refresh token during explicit logout."""
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.token_hash == _refresh_hash(jti),
        )
    )
    current = result.scalar_one_or_none()
    if current is not None and current.revoked_at is None:
        current.revoked_at = datetime.now(UTC)
        await db.commit()


def issue_access_token(user: User) -> str:
    """Compatibility helper for code paths that only need a short access token."""
    return _access_token(user)


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
