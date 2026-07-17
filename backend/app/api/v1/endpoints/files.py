"""文件工作区端点。对齐 PRD 6.7。

用户级文件工作区: 上传 / 列表 / 下载 / 删除 / 分享链接。
存储复用 MinIO (路径 /workspaces/{user_id}/{file_id}/{filename})。
"""

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.core.config import settings
from app.core.deps import CurrentUser, DBSession
from app.core.minio_client import (
    delete_file,
    download_file,
    get_presigned_url,
    upload_file,
)
from app.models.workspace_file import WorkspaceFile
from app.schemas.file import FileRead, FileShareResponse

router = APIRouter(prefix="/files", tags=["文件工作区"])


@router.post("", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_workspace_file(
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """上传文件到个人工作区。"""
    file_data = await file.read()
    if len(file_data) > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件超过大小限制 ({settings.max_upload_size // 1024 // 1024}MB)",
        )
    if not file_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")

    file_id = uuid.uuid4()
    filename = file.filename or "untitled"
    object_name = f"workspaces/{current_user.id}/{file_id}/{filename}"

    upload_file(object_name, file_data, file.content_type or "application/octet-stream")

    wf = WorkspaceFile(
        id=file_id,
        owner_id=current_user.id,
        filename=filename,
        object_name=object_name,
        file_size=len(file_data),
        content_type=file.content_type or "application/octet-stream",
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return FileRead.model_validate(wf)


@router.get("", response_model=list[FileRead])
async def list_workspace_files(current_user: CurrentUser, db: DBSession):
    """列出当前用户工作区文件。"""
    result = await db.execute(
        select(WorkspaceFile)
        .where(WorkspaceFile.owner_id == current_user.id)
        .order_by(WorkspaceFile.created_at.desc())
    )
    return [FileRead.model_validate(f) for f in result.scalars().all()]


@router.get("/{file_id}")
async def download_workspace_file(file_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """下载工作区文件。"""
    wf = await _get_owned_file(db, file_id, current_user.id)
    data = download_file(wf.object_name)
    return Response(
        content=data,
        media_type=wf.content_type,
        headers={"Content-Disposition": f'attachment; filename="{wf.filename}"'},
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_file(file_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """删除工作区文件 (含 MinIO 对象)。"""
    wf = await _get_owned_file(db, file_id, current_user.id)
    try:
        delete_file(wf.object_name)
    except Exception:
        pass
    await db.delete(wf)
    await db.commit()


@router.get("/{file_id}/share", response_model=FileShareResponse)
async def share_workspace_file(file_id: uuid.UUID, current_user: CurrentUser, db: DBSession):
    """生成预签名分享链接 (默认 1 小时有效)。"""
    wf = await _get_owned_file(db, file_id, current_user.id)
    url = get_presigned_url(wf.object_name, expires_hours=1)
    return FileShareResponse(url=url, expires_hours=1)


async def _get_owned_file(db, file_id, owner_id) -> WorkspaceFile:
    result = await db.execute(
        select(WorkspaceFile).where(
            WorkspaceFile.id == file_id, WorkspaceFile.owner_id == owner_id
        )
    )
    wf = result.scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return wf
