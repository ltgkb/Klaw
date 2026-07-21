"""知识库端点测试。

DB 层用 SQLite 内存库 (conftest.py)。
ES/MinIO/TEI 外部服务通过 monkeypatch mock, 确保测试不依赖基础设施。
"""

import io
import uuid

import pytest

from app.services import document_service, kb_service


# ── 辅助函数 ──

async def _register_and_login(client, email="kbuser@test.com", password="secret123"):
    """注册并登录，返回 access_token。"""
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "KB User", "password": password,
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return resp.json()["access_token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ── Mock 外部服务 ──

@pytest.fixture
def mock_infra(monkeypatch, db_engine):
    """Mock ES/MinIO/TEI, 使测试不依赖外部服务。

    同时将 parse_and_index 使用的 async_session_factory 替换为测试 SQLite factory,
    否则后台任务会连接生产 PG 并触发跨事件循环错误。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import app.core.database as db_module

    test_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "async_session_factory", test_factory)

    # Mock MinIO (document_service 导入: upload_file, download_file, delete_file — 都是同步函数)
    def mock_upload_file(object_name, data, content_type="application/octet-stream"):
        return object_name
    def mock_download_file(object_name):
        return b"mock file content"
    def mock_delete_file(object_name):
        pass
    monkeypatch.setattr("app.services.document_service.upload_file", mock_upload_file)
    monkeypatch.setattr("app.services.document_service.download_file", mock_download_file)
    monkeypatch.setattr("app.services.document_service.delete_file", mock_delete_file)
    # kb_service 也导入了 delete_file
    monkeypatch.setattr("app.services.kb_service.delete_file", mock_delete_file)

    # Mock TEI (document_service 导入: embed_texts, embed_query)
    async def mock_embed_texts(texts, timeout=60.0):
        return [[0.1] * 1024 for _ in texts]
    async def mock_embed_query(text, timeout=10.0):
        return [0.1] * 1024
    monkeypatch.setattr("app.services.document_service.embed_texts", mock_embed_texts)
    monkeypatch.setattr("app.services.document_service.embed_query", mock_embed_query)

    # Mock ES (document_service 导入: index_chunks_bulk, es_hybrid_search, delete_doc_chunks)
    async def mock_index_chunks_bulk(chunks):
        return len(chunks)
    async def mock_hybrid_search(kb_id, query_vector, query_text, top_k=10, num_candidates=200):
        return [{
            "chunk_id": "mock-chunk-1",
            "doc_id": "mock-doc-1",
            "content": "mock content for " + query_text,
            "content_type": "text",
            "page": 0,
            "score": 0.95,
            "metadata": {},
        }]
    async def mock_delete_doc_chunks(doc_id):
        return 1
    # kb_service 导入了 delete_kb_chunks
    async def mock_delete_kb_chunks(kb_id):
        return 1
    monkeypatch.setattr("app.services.document_service.index_chunks_bulk", mock_index_chunks_bulk)
    monkeypatch.setattr("app.services.document_service.es_hybrid_search", mock_hybrid_search)
    monkeypatch.setattr("app.services.document_service.delete_doc_chunks", mock_delete_doc_chunks)
    monkeypatch.setattr("app.services.kb_service.delete_kb_chunks", mock_delete_kb_chunks)

    # Mock DeepDoc parse (document_service 导入 deepdoc_service 模块)
    def mock_parse_document(filename, file_data, chunk_token_num=128):
        return [
            {"content": "这是第一段文本内容。", "content_type": "text", "page": 0},
            {"content": "这是第二段文本内容。", "content_type": "text", "page": 0},
        ]
    monkeypatch.setattr("app.services.deepdoc_service.parse_document", mock_parse_document)


# ── 知识库 CRUD 测试 ──

@pytest.mark.asyncio
async def test_create_kb(client):
    token = await _register_and_login(client)
    resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "测试知识库",
        "description": "用于测试",
    }, headers=_auth_headers(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试知识库"
    assert data["description"] == "用于测试"
    assert data["embedding_model"] == "BGE-M3"
    assert data["chunk_strategy"] == "recursive"
    assert data["document_count"] == 0
    assert data["status"] == "active"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_kb_unauthorized(client):
    resp = await client.post("/api/v1/knowledge-bases", json={"name": "test"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_kbs(client):
    token = await _register_and_login(client)
    # 创建 2 个知识库
    for i in range(2):
        await client.post("/api/v1/knowledge-bases", json={
            "name": f"KB-{i}", "description": f"desc-{i}",
        }, headers=_auth_headers(token))

    resp = await client.get("/api/v1/knowledge-bases", headers=_auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_kb(client):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "GetTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "GetTest"


@pytest.mark.asyncio
async def test_get_kb_not_found(client):
    token = await _register_and_login(client)
    resp = await client.get("/api/v1/knowledge-bases/00000000-0000-0000-0000-000000000000", headers=_auth_headers(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_kb(client):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "OldName",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.put(f"/api/v1/knowledge-bases/{kb_id}", json={
        "name": "NewName", "description": "updated",
    }, headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"
    assert resp.json()["description"] == "updated"


@pytest.mark.asyncio
async def test_delete_kb(client):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "ToDelete",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/knowledge-bases/{kb_id}", headers=_auth_headers(token))
    assert resp.status_code == 204

    # 确认已删除
    resp2 = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=_auth_headers(token))
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_kb_owner_isolation(client):
    """用户 A 不能看到用户 B 的知识库。"""
    token_a = await _register_and_login(client, "userA@test.com")
    token_b = await _register_and_login(client, "userB@test.com")

    # A 创建知识库
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "A's KB",
    }, headers=_auth_headers(token_a))
    kb_id = create_resp.json()["id"]

    # B 看不到 A 的知识库
    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}", headers=_auth_headers(token_b))
    assert resp.status_code == 404

    # B 列表为空
    list_resp = await client.get("/api/v1/knowledge-bases", headers=_auth_headers(token_b))
    assert list_resp.json()["total"] == 0


# ── 文档上传测试 ──

@pytest.mark.asyncio
async def test_upload_document(client, mock_infra):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "UploadTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    # 上传 TXT 文件
    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"Hello world test content"), "text/plain")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "test.txt"
    assert data["parse_status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_upload_document_kb_not_found(client, mock_infra):
    token = await _register_and_login(client)
    resp = await client.post(
        "/api/v1/knowledge-bases/00000000-0000-0000-0000-000000000000/documents",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"test"), "text/plain")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_documents(client, mock_infra):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "DocListTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    # 上传 2 个文档
    for i in range(2):
        await client.post(
            f"/api/v1/knowledge-bases/{kb_id}/documents",
            headers=_auth_headers(token),
            files={"file": (f"test{i}.txt", io.BytesIO(b"content"), "text/plain")},
        )

    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_delete_document(client, mock_infra):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "DeleteDocTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
    )
    doc_id = upload_resp.json()["id"]

    resp = await client.delete(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 204

    # 确认已删除
    list_resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=_auth_headers(token))
    assert len(list_resp.json()) == 0


# ── 检索测试 ──

@pytest.mark.asyncio
async def test_search(client, mock_infra):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "SearchTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/search",
        headers=_auth_headers(token),
        json={"query": "测试查询", "top_k": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "测试查询"
    assert data["total"] >= 1
    assert len(data["hits"]) >= 1
    assert "content" in data["hits"][0]
    assert "score" in data["hits"][0]


@pytest.mark.asyncio
async def test_search_with_threshold(client, mock_infra):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "ThresholdTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    # threshold=1.0 应过滤掉 score=0.95 的结果
    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/search",
        headers=_auth_headers(token),
        json={"query": "test", "top_k": 5, "threshold": 1.0},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── Chunk 列表测试 ──

@pytest.mark.asyncio
async def test_list_chunks_empty(client, mock_infra):
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "ChunkTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/chunks", headers=_auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ── 异步解析管线测试 ──

@pytest.mark.asyncio
async def test_parse_and_index_pipeline(client, mock_infra):
    """测试后台解析管线: upload → parse → chunk → embed → ES index。

    async_session_factory 已在 mock_infra fixture 中替换为 SQLite factory。
    """
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "PipelineTest",
        "chunk_strategy": "recursive",
        "chunk_size": 256,
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    # 上传文档 (BackgroundTasks 在 TestClient 中同步执行)
    upload_resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"Hello world test content for pipeline"), "text/plain")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    # 检查文档解析状态 — BackgroundTasks 已同步完成
    docs_resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=_auth_headers(token))
    docs = docs_resp.json()
    assert len(docs) == 1
    # 解析应已完成
    assert docs[0]["parse_status"] == "parsed", f"Expected parsed, got {docs[0]['parse_status']}"

    # 检查 chunk 是否已创建
    chunks_resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/chunks", headers=_auth_headers(token))
    assert chunks_resp.status_code == 200
    assert chunks_resp.json()["total"] >= 1, "Should have chunks after parsing"


# ── WP7: 扩展名校验 / 重解析 / 失败置 failed ──

@pytest.mark.asyncio
async def test_upload_unsupported_extension_415(client, mock_infra):
    """不支持的文件扩展名应返回 415。"""
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "ExtTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("evil.exe", io.BytesIO(b"MZ binary"), "application/octet-stream")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_reparse_document(client, mock_infra):
    """reparse 端点: 重置状态并后台重新解析, 最终回到 parsed。"""
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "ReparseTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"reparse content"), "text/plain")},
    )
    doc_id = upload_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/{doc_id}/reparse",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    # 响应在后台任务执行前序列化 → pending; 后台任务同步执行完毕 → parsed
    assert resp.json()["parse_status"] == "pending"

    docs_resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=_auth_headers(token))
    assert docs_resp.json()[0]["parse_status"] == "parsed"

    # chunk 仍然存在 (重新生成, 非重复累积)
    chunks_resp = await client.get(
        f"/api/v1/knowledge-bases/{kb_id}/chunks", headers=_auth_headers(token)
    )
    assert chunks_resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_reparse_document_not_found(client, mock_infra):
    """reparse 不存在的文档应 404。"""
    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "Reparse404",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents/00000000-0000-0000-0000-000000000000/reparse",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_parse_failure_marks_failed_with_error(client, mock_infra, monkeypatch, db_engine):
    """向量化维度不符 → 管线 raise → 文档置 failed, 失败原因写入 parse_result。"""
    async def bad_embed_texts(texts, timeout=60.0):
        raise ValueError("向量维度不符: 期望 1024, 实际 512")
    monkeypatch.setattr("app.services.document_service.embed_texts", bad_embed_texts)

    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "FailTest",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"will fail"), "text/plain")},
    )
    assert upload_resp.status_code == 201
    doc_id = upload_resp.json()["id"]

    docs_resp = await client.get(f"/api/v1/knowledge-bases/{kb_id}/documents", headers=_auth_headers(token))
    assert docs_resp.json()[0]["parse_status"] == "failed"

    # parse_result 含失败原因 (DocumentRead 不暴露该字段, 直接查 DB)
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models.document import Document

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(select(Document).where(Document.id == uuid.UUID(doc_id)))
        doc = result.scalar_one()
    assert doc.parse_result is not None
    assert "维度不符" in doc.parse_result["error"]


@pytest.mark.asyncio
async def test_search_backend_error_returns_503(client, mock_infra, monkeypatch):
    """ES 检索异常应转为 503, 而非 500 内部错误。"""
    async def boom_search(**kwargs):
        raise ConnectionError("ES unreachable")
    monkeypatch.setattr("app.services.document_service.es_hybrid_search", boom_search)

    token = await _register_and_login(client)
    create_resp = await client.post("/api/v1/knowledge-bases", json={
        "name": "Search503",
    }, headers=_auth_headers(token))
    kb_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/knowledge-bases/{kb_id}/search",
        headers=_auth_headers(token),
        json={"query": "测试", "top_k": 5},
    )
    assert resp.status_code == 503
