"""Helpers for inspecting FastAPI's spooled UploadFile without reading it all."""

import asyncio

from fastapi import UploadFile


def _size_and_rewind(file_object) -> int:
    file_object.seek(0, 2)
    size = file_object.tell()
    file_object.seek(0)
    return size


async def get_upload_size(upload: UploadFile) -> int:
    """Return the spooled file size and rewind it, without allocating file bytes."""
    return await asyncio.to_thread(_size_and_rewind, upload.file)
