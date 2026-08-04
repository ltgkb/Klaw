"""Upload spooling and MinIO streaming regression tests."""

import io

import pytest
from fastapi import UploadFile

from app.core import minio_client
from app.core.upload import get_upload_size


class _NoReadBytesIO(io.BytesIO):
    def read(self, *args, **kwargs):
        raise AssertionError("size inspection must not read file contents")


@pytest.mark.asyncio
async def test_get_upload_size_uses_seek_and_rewinds():
    stream = _NoReadBytesIO(b"streamed-content")
    upload = UploadFile(file=stream, filename="large.bin")
    assert await get_upload_size(upload) == len(b"streamed-content")
    assert stream.tell() == 0


def test_minio_stream_rewinds_for_storage_retry(monkeypatch):
    payload = b"retry-safe-stream"
    stream = io.BytesIO(payload)
    attempts: list[bytes] = []

    class _Client:
        def put_object(self, *, data, length, **kwargs):
            attempts.append(data.read(length))

    monkeypatch.setattr(minio_client, "get_minio_client", lambda: _Client())

    def run_twice(operation):
        operation()
        operation()

    monkeypatch.setattr(minio_client, "_with_bucket_retry", run_twice)
    minio_client.upload_stream("objects/test.bin", stream, len(payload))
    assert attempts == [payload, payload]
