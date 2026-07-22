"""应用配置，从环境变量读取。对齐 PRD 第 4 节技术栈与第 7 节集成方案。"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
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
    access_token_expire_minutes: int = 720  # 12 小时
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

    # ── Embedding 模型 API (OpenAI 兼容 /v1/embeddings, 优先于 TEI) ──
    # 配置后向量化走此 API; 留空则回落 TEI, 再回落 dev 哈希兜底。
    embedding_api_base_url: str = ""
    embedding_api_key: str = ""
    embedding_api_model: str = ""

    # ── Redis (缓存 + Celery broker + 分布式锁) ──
    redis_url: str = "redis://localhost:6379/0"

    # ── MinIO (对象存储 + 文件工作区) ──
    minio_url: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "claw-workspaces"
    # 对外可访问的 MinIO URL (share 链接用); 留空回落 minio_url
    minio_public_url: str | None = None

    # ── 文件上传限制 ──
    max_upload_size: int = 100 * 1024 * 1024  # 100 MB

    # ── 本地 Agent: OpenClaw ──
    openclaw_url: str = "http://localhost:8080"
    openclaw_token: str = ""  # Gateway auth token (--auth token --token xxx)
    # Gateway tools can remain available while model routing is intentionally disabled.
    # Opt in only after the gateway has a usable inference provider. OpenClaw's
    # /v1/models endpoint exposes agent aliases even when upstream auth is absent.
    openclaw_chat_enabled: bool = False

    # ── 本地 Agent: Hermes ──
    hermes_url: str = "http://localhost:8081"
    hermes_api_server_key: str = ""
    hermes_chat_enabled: bool = False

    # ── Cross-Encoder 重排序 (TEI reranker sidecar) ──
    reranker_url: str = "http://localhost:8083"

    # ── 定时任务 ──
    scheduler_timezone: str = "Asia/Shanghai"

    # ── Fallback 模型供应商 ──
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Kaiweb API (自建 OpenAI 兼容网关, https://ai.kaiweb.net) ──
    # 优先级最高的真实 LLM 供应商; dev 环境配置 Key 后即取代 Mock 兜底。
    kaiweb_base_url: str = "https://ai.kaiweb.net/v1"
    kaiweb_api_key: str = ""
    kaiweb_model: str = "glm-4.5-air"

    # ── CORS ──
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    @model_validator(mode="after")
    def _reject_default_secrets_in_prod(self) -> "Settings":
        """prod 环境启动校验：拒绝默认 JWT/加密密钥，防止弱密钥上线。"""
        if self.environment == "prod":
            if self.jwt_secret_key == "change-me-in-production-please-use-a-long-random-string":
                raise ValueError(
                    "prod 环境必须通过 JWT_SECRET_KEY 设置强随机密钥"
                )
            if self.encryption_key == "0" * 64:
                raise ValueError(
                    "prod 环境必须通过 ENCRYPTION_KEY 设置真实加密密钥 "
                    "(python -c \"import secrets; print(secrets.token_hex(32))\")"
                )
        return self

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
