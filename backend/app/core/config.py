"""应用配置，从环境变量读取。对齐 PRD 第 4 节技术栈与第 7 节集成方案。"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 应用 ──
    app_name: str = "Claw-Native Agent Platform"
    environment: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # ── 安全 ──
    jwt_secret_key: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    # AES-256-GCM 主密钥 (32 bytes, hex 编码 64 字符)
    encryption_key: str = "0" * 64  # 生产环境必须替换

    # ── PostgreSQL (元数据 + 记忆 + 定时任务 JobStore) ──
    postgres_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/claw_agent"

    # ── Elasticsearch (向量 + 全文检索) ──
    es_url: str = "http://localhost:9200"
    # 知识库 chunk 索引名 (M2)
    es_kb_index: str = "claw-kb-chunks"

    # ── TEI: Text Embeddings Inference sidecar (BGE-M3) ──
    tei_url: str = "http://localhost:8082"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    # ── Redis (缓存 + Celery broker + 分布式锁) ──
    redis_url: str = "redis://localhost:6379/0"

    # ── MinIO (对象存储 + 文件工作区) ──
    minio_url: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "claw-workspaces"

    # ── 文件上传限制 ──
    max_upload_size: int = 100 * 1024 * 1024  # 100 MB

    # ── 本地 Agent: OpenClaw ──
    openclaw_url: str = "http://localhost:8080"
    openclaw_token: str = ""  # Gateway auth token (--auth token --token xxx)

    # ── 本地 Agent: Hermes ──
    hermes_url: str = "http://localhost:8081"

    # ── Cross-Encoder 重排序 (TEI reranker sidecar) ──
    reranker_url: str = "http://localhost:8083"

    # ── Fallback 模型供应商 ──
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── CORS ──
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @property
    def sync_postgres_url(self) -> str:
        """Alembic 用同步驱动 URL。"""
        return self.postgres_url.replace("+asyncpg", "+psycopg2").replace(
            "+asyncpg", ""
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
