"""本地 Agent (OpenClaw / Hermes) 工具发现 Pydantic 模型。对齐 PRD 6.4。"""

from typing import Any

from pydantic import BaseModel


class ToolInfo(BaseModel):
    """本地工具 (Skill) 信息。"""

    id: str
    name: str
    description: str | None = None
    source: str = "local"  # local (skills 目录) / openclaw / hermes
    parameters: dict[str, Any] | None = None  # 参数 schema


class ToolCallRequest(BaseModel):
    """工具调用请求。"""

    parameters: dict[str, Any] = {}


class ToolCallResponse(BaseModel):
    """工具调用响应。"""

    tool_id: str
    success: bool
    result: Any = None
    error: str | None = None
    source: str = "mock"  # openclaw / mock


class LocalAgentHealth(BaseModel):
    """本地 Agent 健康状态。"""

    openclaw: bool
    hermes: bool
    openclaw_url: str
    hermes_url: str
