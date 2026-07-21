"""知识库管理端点。对齐 PRD 6.1 知识库 API。

完整 CRUD + 文档上传 + 异步解析 + 混合检索。
"""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import CurrentUser, DBSession
from app.schemas.common import APIResponse, PageResponse
from app.schemas.knowledge_base import (
    ChunkRead,
    DocumentRead,
    DocumentUploadResponse,
    KBCreate,
    KBRead,
    KBUpdate,
    SearchRequest,
    SearchResponse,
)
from app.services import deepdoc_service, document_service, kb_service

router = APIRouter(prefix="/knowledge-bases", tags=["知识库"])


# ── 知识库 CRUD ──

@router.post("", response_model=KBRead, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base(
    data: KBCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """创建知识库。"""
    kb = await kb_service.create_kb(db, current_user.id, data)
    return KBRead.model_validate(kb)


@router.get("", response_model=PageResponse[KBRead])
async def list_knowledge_bases(
    current_user: CurrentUser,
    db: DBSession,
    page: int = 1,
    page_size: int = 20,
):
    """列出当前用户的知识库。"""
    items, total = await kb_service.list_kbs(db, current_user.id, page, page_size)
    return PageResponse(items=[KBRead.model_validate(kb) for kb in items], total=total, page=page, page_size=page_size)


@router.get("/{kb_id}", response_model=KBRead)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """获取知识库详情。"""
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return KBRead.model_validate(kb)


@router.put("/{kb_id}", response_model=KBRead)
async def update_knowledge_base(
    kb_id: uuid.UUID,
    data: KBUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """更新知识库元数据。"""
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    kb = await kb_service.update_kb(db, kb, data)
    return KBRead.model_validate(kb)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """删除知识库及其所有文档、chunk、ES 索引。"""
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    await kb_service.delete_kb(db, kb)


# ── 文档管理 ──

@router.post("/{kb_id}/documents", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    """上传文档到知识库，后台自动解析+分块+向量化+索引。

    支持: PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, JSON, EPUB
    """
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    # 校验文件扩展名 (与 DeepDoc 支持的 parser 类型一致)
    filename = file.filename or "untitled"
    if deepdoc_service.get_parser_type(filename) is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支持的文件类型: {filename}",
        )

    # 读取文件内容
    file_data = await file.read()
    if len(file_data) > settings.max_upload_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"文件超过大小限制 ({settings.max_upload_size // 1024 // 1024}MB)",
        )
    if not file_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空")

    # 上传到 MinIO + 创建 DB 记录
    doc = await document_service.upload_document(
        db, kb, file.filename or "untitled", file_data, file.content_type or "application/octet-stream"
    )

    # 后台异步解析+索引
    background_tasks.add_task(document_service.parse_and_index, doc.id, kb.id)

    return DocumentUploadResponse(
        id=doc.id,
        kb_id=doc.kb_id,
        filename=doc.filename,
        file_size=doc.file_size,
        parse_status=doc.parse_status,
    )


@router.get("/{kb_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """列出知识库下的文档。"""
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    docs = await document_service.list_documents(db, kb_id)
    return [DocumentRead.model_validate(d) for d in docs]


@router.delete("/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """删除文档及其 chunk 和 ES 索引。"""
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    doc = await document_service.get_document(db, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")
    await document_service.delete_document(db, doc)


@router.post("/{kb_id}/documents/{doc_id}/reparse", response_model=DocumentRead)
async def reparse_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: DBSession,
):
    """重新解析文档: 清除旧 chunk 后后台重新执行 解析→分块→向量化→索引 管线。"""
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    doc = await document_service.get_document(db, doc_id)
    if doc is None or doc.kb_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    await document_service.reset_document_for_reparse(db, doc)
    background_tasks.add_task(document_service.parse_and_index, doc.id, kb.id)
    return DocumentRead.model_validate(doc)


# ── Chunk 查询 ──

@router.get("/{kb_id}/chunks", response_model=PageResponse[ChunkRead])
async def list_chunks(
    kb_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
    doc_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """列出知识库的 chunk。可按 doc_id 过滤。"""
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    chunks, total = await document_service.list_chunks(db, kb_id, doc_id, page, page_size)
    return PageResponse(
        items=[ChunkRead.model_validate(c) for c in chunks],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── 混合检索 ──

@router.post("/{kb_id}/search", response_model=SearchResponse)
async def search_knowledge_base(
    kb_id: uuid.UUID,
    request: SearchRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """混合检索: TEI 向量化 query → ES kNN (向量) + BM25 (全文)。

    返回 top_k 条结果, 按 score 排序。
    """
    kb = await kb_service.get_kb(db, kb_id, current_user.id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")
    return await document_service.search(db, kb_id, request)
