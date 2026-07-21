"""AES-256-GCM 加解密、bcrypt 密码与 prod 密钥启动校验测试 (WP1)。"""

import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.core.security import hash_password, verify_password
from app.utils.crypto import decrypt, encrypt


# ── AES-256-GCM 加解密 ──


def test_encrypt_decrypt_roundtrip():
    """加密后解密应还原明文。"""
    plaintext = "sk-test-key-12345"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_encrypt_decrypt_unicode_roundtrip():
    """含中文/emoji 的明文也应正确往返。"""
    plaintext = "密钥-测试-🔑"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_encrypt_uses_random_nonce():
    """同一明文两次加密应产生不同密文 (随机 nonce)。"""
    plaintext = "same-input"
    assert encrypt(plaintext) != encrypt(plaintext)


def test_decrypt_tampered_ciphertext_raises():
    """篡改密文应校验失败抛 InvalidTag，而非静默解密。"""
    token = encrypt("secret")
    raw = bytearray(base64.b64decode(token))
    raw[-1] ^= 0xFF
    tampered = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(InvalidTag):
        decrypt(tampered)


# ── bcrypt 72 字节上限 ──


def test_long_password_over_72_bytes_roundtrip():
    """超过 72 字节的密码应截断后正常哈希/校验，不抛 ValueError (P2-7)。"""
    password = "长密码" * 40  # 360 字节，远超 72
    hashed = hash_password(password)
    assert verify_password(password, hashed)
    assert not verify_password("完全不同的短密码", hashed)


def test_verify_password_invalid_hash_returns_false():
    """非法哈希值应返回 False 而非抛异常。"""
    assert verify_password("secret123", "not-a-bcrypt-hash") is False


# ── prod 默认密钥启动校验 (P1-2) ──


def test_prod_rejects_default_secrets(monkeypatch):
    """prod 环境下使用默认 JWT/加密密钥应拒绝启动。"""
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(environment="prod", _env_file=None)


def test_prod_accepts_strong_secrets(monkeypatch):
    """prod 环境下设置强密钥可正常启动。"""
    from app.core.config import Settings

    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("ENCRYPTION_KEY", "b" * 64)
    s = Settings(environment="prod", _env_file=None)
    assert s.environment == "prod"


def test_contract_fields_defaults():
    """跨包契约 1：scheduler_timezone / minio_public_url 默认值。"""
    from app.core.config import settings

    assert settings.scheduler_timezone == "Asia/Shanghai"
    assert settings.minio_public_url is None
