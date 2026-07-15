"""MinIO 对象存储客户端。

对齐 PRD 第 5.1 节: 文档上传后存储到 MinIO，解析时按需下载。
"""

import io
import logging
from datetime import timedelta

from minio import Minio

from app.core.config import settings

logger = logging.getLogger("claw.minio")

_client: Minio | None = None


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
    """确保 bucket 存在。"""
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
        logger.info("MinIO bucket 创建: %s", settings.minio_bucket)
    else:
        logger.info("MinIO bucket 已存在: %s", settings.minio_bucket)


def upload_file(object_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """上传文件到 MinIO，返回 object_name (后续可用于生成 URL / 下载)。

    object_name 建议格式: {kb_id}/{doc_id}/{filename}
    """
    client = get_minio_client()
    client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=object_name,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    logger.info("MinIO 上传成功: %s (%d bytes)", object_name, len(data))
    return object_name


def download_file(object_name: str) -> bytes:
    """从 MinIO 下载文件，返回字节内容。"""
    client = get_minio_client()
    response = client.get_object(settings.minio_bucket, object_name)
    try:
        data = response.read()
    finally:
        response.close()
        response.release_conn()
    logger.info("MinIO 下载: %s (%d bytes)", object_name, len(data))
    return data


def get_presigned_url(object_name: str, expires_hours: int = 1) -> str:
    """生成预签名下载 URL。"""
    client = get_minio_client()
    url = client.presigned_get_object(
        settings.minio_bucket,
        object_name,
        expires=timedelta(hours=expires_hours),
    )
    return url


def delete_file(object_name: str) -> None:
    """从 MinIO 删除文件。"""
    client = get_minio_client()
    client.remove_object(settings.minio_bucket, object_name)
    logger.info("MinIO 删除: %s", object_name)
