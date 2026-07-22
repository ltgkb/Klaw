"""JWT 生成/校验 + 密码哈希。对齐 PRD 3.3.3 与 8.2。"""

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


# ── 密码 ──

_BCRYPT_SHA256_PREFIX = "bcrypt-sha256$"

def _to_bcrypt_bytes(password: str) -> bytes:
    """Legacy bcrypt normalization retained only for existing hashes."""
    return password.encode("utf-8")[:72]


def _to_bcrypt_sha256_bytes(password: str) -> bytes:
    """Pre-hash to a fixed safe length so bcrypt covers the complete password."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def hash_password(password: str) -> str:
    """Hash the complete password with a versioned bcrypt-SHA256 scheme."""
    hashed = bcrypt.hashpw(_to_bcrypt_sha256_bytes(password), bcrypt.gensalt()).decode("ascii")
    return _BCRYPT_SHA256_PREFIX + hashed


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希。"""
    try:
        if hashed.startswith(_BCRYPT_SHA256_PREFIX):
            encoded = _to_bcrypt_sha256_bytes(plain)
            stored = hashed[len(_BCRYPT_SHA256_PREFIX):]
        else:
            encoded = _to_bcrypt_bytes(plain)
            stored = hashed
        return bcrypt.checkpw(encoded, stored.encode("ascii"))
    except (ValueError, TypeError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    """Return true for legacy raw-bcrypt hashes that can be upgraded safely."""
    return not hashed.startswith(_BCRYPT_SHA256_PREFIX)


# ── JWT ──

def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """生成短时效 access token。"""
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    """生成长时效 refresh token。"""
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    """解码并校验 JWT，失败返回 None。"""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
