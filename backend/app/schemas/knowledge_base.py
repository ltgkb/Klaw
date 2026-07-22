"""知识库相关 Pydantic 模型。对齐 PRD 6.1 知识库 API。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.document import ParseStatus
from app.models.knowledge_base import ChunkStrategy, KBStatus
from app.models.chunk import ContentType


# ── 知识库 ──

class KBCreate(BaseModel):
    """创建知识库。"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    embedding_model: str = "BGE-M3"
    chunk_strategy: ChunkStrategy = ChunkStrategy.recursive
    chunk_size: int = Field(512, ge=100, le=4096)
    chunk_overlap: int = Field(50, ge=0, le=512)

    @model_validator(mode="after")
    def validate_chunk_window(self) -> "KBCreate":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        return self


class KBUpdate(BaseModel):
    """更新知识库。"""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None


class KBRead(BaseModel):
    """知识库响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    embedding_model: str
    chunk_strategy: ChunkStrategy
    chunk_size: int
    chunk_overlap: int
    document_count: int
    status: KBStatus
    created_at: datetime
    updated_at: datetime


# ── 文档 ──

class DocumentRead(BaseModel):
    """文档响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    file_size: int
    page_count: int
    parse_status: ParseStatus
    parse_error: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentUploadResponse(BaseModel):
    """上传文档响应。"""
    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    file_size: int
    parse_status: ParseStatus
    message: str = "文档已上传，正在后台解析"


# ── Chunk ──

class ChunkRead(BaseModel):
    """Chunk 响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_id: uuid.UUID
    kb_id: uuid.UUID
    content: str
    content_type: ContentType
    page: int
    embedding_stored: bool
    created_at: datetime


# ── 检索 ──

class SearchRequest(BaseModel):
    """混合检索请求。"""
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=100)
    threshold: float = Field(0.0, ge=0.0, le=1.0)
    # Cross-Encoder 重排序 (M4)
    rerank: bool = False
    rerank_top_k: int | None = Field(None, ge=1, le=100)


class SearchHit(BaseModel):
    """单条检索结果。"""
    chunk_id: str
    doc_id: str
    content: str
    content_type: str
    page: int
    score: float
    metadata: dict = {}
    # Cross-Encoder 重排序分数 (rerank=True 时填充)
    rerank_score: float | None = None


class SearchResponse(BaseModel):
    """检索响应。"""
    query: str
    total: int
    hits: list[SearchHit]
