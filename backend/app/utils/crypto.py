"""AES-256-GCM 加解密工具，用于 API Key 等敏感字段存储。对齐 PRD 8.2 安全要求。"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# AES-256 需要 32 字节密钥
_KEY = bytes.fromhex(settings.encryption_key)
if len(_KEY) != 32:
    raise ValueError("encryption_key 必须是 64 位 hex 字符 (32 字节)")


def encrypt(plaintext: str) -> str:
    """加密明文，返回 base64(nonce + ciphertext)。

    GCM 模式每次加密生成 12 字节随机 nonce，附在密文前。
    """
    nonce = os.urandom(12)
    aesgcm = AESGCM(_KEY)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str) -> str:
    """解密 encrypt() 的输出，返回明文。"""
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_KEY)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


class EncryptedString:
    """SQLAlchemy 类型装饰器思路（简化版）：
    存入 DB 前加密，读取时解密。在 model 层手动调用 encrypt/decrypt 即可。
    """

    @staticmethod
    def process_bind(value: str | None) -> str | None:
        if value is None:
            return None
        return encrypt(value)

    @staticmethod
    def process_result(value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return decrypt(value)
        except Exception:
            # 解密失败说明存的是明文或密钥变更，返回原值
            return value
