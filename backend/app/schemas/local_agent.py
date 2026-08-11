"""本地 Agent (OpenClaw / Hermes) 工具发现 Pydantic 模型。对齐 PRD 6.4。"""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ToolInfo(BaseModel):
    """本地工具 (Skill) 信息。"""

    id: str
    name: str
    description: str | None = None
    source: str = "local"  # local (skills 目录) / openclaw / hermes
    parameters: dict[str, Any] | None = None  # 参数 schema
    executable: bool = True


class ToolCallRequest(BaseModel):
    """工具调用请求。"""

    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    """工具调用响应。"""

    tool_id: str
    success: bool
    result: Any = None
    error: str | None = None
    source: str = "openclaw"  # openclaw / mock


class LocalAgentHealth(BaseModel):
    """本地 Agent 健康状态。"""

    openclaw: bool
    hermes: bool
    openclaw_url: str
    hermes_url: str


class McpServerCreate(BaseModel):
    """Create and verify a remote Streamable HTTP MCP connection."""

    name: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., min_length=8, max_length=2048)
    bearer_token: str | None = Field(None, max_length=4096)


class McpServerRead(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    has_token: bool
    enabled: bool
    tools: list[dict[str, Any]] = Field(default_factory=list)


class McpServerTestResponse(BaseModel):
    success: bool = True
    protocol_version: str
    server_info: dict[str, Any] = Field(default_factory=dict)
    server: McpServerRead
