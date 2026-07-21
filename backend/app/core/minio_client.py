"""MinIO 对象存储客户端。

对齐 PRD 第 5.1 节: 文档上传后存储到 MinIO，解析时按需下载。
"""

import io
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import TypeVar
from urllib.parse import urlsplit, urlunsplit

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger("claw.minio")

_client: Minio | None = None
# ensure_bucket 成功缓存: 避免每次请求都做一次 bucket_exists 网络探测
_bucket_ready: bool = False


def get_minio_client() -> Minio:
    """获取 Minio 单例。"""
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_url,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
    return _client


def ensure_bucket() -> None:
    """确保 bucket 存在 (成功后写入缓存标记)。"""
    global _bucket_ready
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        logger.info("MinIO bucket 创建: %s", settings.minio_bucket)
    else:
        logger.info("MinIO bucket 已存在: %s", settings.minio_bucket)
    _bucket_ready = True


def _ensure_bucket_cached() -> None:
    """带缓存的 ensure_bucket: 已成功过则跳过网络探测。"""
    if not _bucket_ready:
        ensure_bucket()


T = TypeVar("T")


def _with_bucket_retry(op: Callable[[], T]) -> T:
    """执行 MinIO 操作; S3Error 时重置缓存重建 bucket 并重试一次。"""
    global _bucket_ready
    _ensure_bucket_cached()
    try:
        return op()
    except S3Error:
        logger.warning("MinIO 请求失败, 重建 bucket 缓存并重试一次", exc_info=True)
        _bucket_ready = False
        ensure_bucket()
        return op()


def _apply_public_host(url: str) -> str:
    """按部署配置替换预签名 URL 的公网 host (未配置时原样返回)。

    settings.minio_public_url 支持带 scheme (https://files.example.com)
    或纯 host:port 两种写法。
    """
    public = getattr(settings, "minio_public_url", None) or None
    if not public:
        return url
    parts = urlsplit(url)
    if "://" in public:
        p = urlsplit(public)
        return urlunsplit((p.scheme or parts.scheme, p.netloc, parts.path, parts.query, parts.fragment))
    return urlunsplit((parts.scheme, public, parts.path, parts.query, parts.fragment))


def upload_file(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """上传文件到 MinIO，返回 object_name (后续可用于生成 URL / 下载)。

    object_name 建议格式: {kb_id}/{doc_id}/{filename}
    """

    def _put() -> None:
        client = get_minio_client()
        client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    _with_bucket_retry(_put)
    logger.info("MinIO 上传成功: %s (%d bytes)", object_name, len(data))
    return object_name


def download_file(object_name: str) -> bytes:
    """从 MinIO 下载文件，返回字节内容。"""

    def _get() -> bytes:
        client = get_minio_client()
        response = client.get_object(settings.minio_bucket, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    data = _with_bucket_retry(_get)
    logger.info("MinIO 下载: %s (%d bytes)", object_name, len(data))
    return data


def get_presigned_url(object_name: str, expires_hours: int = 1) -> str:
    """生成预签名下载 URL (按配置替换公网 host)。"""

    def _sign() -> str:
        client = get_minio_client()
        return client.presigned_get_object(
            settings.minio_bucket,
            object_name,
            expires=timedelta(hours=expires_hours),
        )

    url = _with_bucket_retry(_sign)
    return _apply_public_host(url)


def delete_file(object_name: str) -> None:
    """从 MinIO 删除文件。"""

    def _remove() -> None:
        client = get_minio_client()
        client.remove_object(settings.minio_bucket, object_name)

    _with_bucket_retry(_remove)
    logger.info("MinIO 删除: %s", object_name)
