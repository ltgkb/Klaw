"""Agent 工作流相关 Pydantic 模型。对齐 PRD 6.2 Agent 画布 API。"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.agent_flow import FlowStatus, TriggerType
from app.models.execution import ExecutionStatus


# ── 工作流 ──

def _reject_inline_notify_channels(dag: dict | None) -> dict | None:
    """Keep channel credentials out of the plaintext workflow JSON."""
    if dag is None:
        return None
    for node in dag.get("nodes", []):
        if node.get("type") != "notify":
            continue
        config = node.get("data", {}).get("config", {})
        if config.get("channels"):
            raise ValueError("通知节点不允许内联渠道配置，请使用已加密保存的 channel_ids")
    return dag


class FlowCreate(BaseModel):
    """创建工作流。"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    dag: dict = Field(default_factory=lambda: {"nodes": [], "edges": []})
    trigger_type: TriggerType = TriggerType.manual
    trigger_config: dict | None = None

    _validate_notify_channels = field_validator("dag")(_reject_inline_notify_channels)


class FlowUpdate(BaseModel):
    """更新工作流。"""
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    dag: dict | None = None
    status: FlowStatus | None = None
    trigger_type: TriggerType | None = None
    trigger_config: dict | None = None

    _validate_notify_channels = field_validator("dag")(_reject_inline_notify_channels)


class FlowRead(BaseModel):
    """工作流响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    dag: dict
    status: FlowStatus
    trigger_type: TriggerType
    trigger_config: dict | None
    created_at: datetime
    updated_at: datetime


# ── 执行 ──

class ExecuteRequest(BaseModel):
    """执行工作流请求。"""
    input: dict[str, Any] = Field(default_factory=dict)


class ExecutionRead(BaseModel):
    """执行记录响应。"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    flow_id: uuid.UUID
    status: ExecutionStatus
    input: dict | None
    output: dict | None
    node_states: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ExecuteResponse(BaseModel):
    """执行触发响应。"""
    execution_id: uuid.UUID
    flow_id: uuid.UUID
    status: ExecutionStatus
    message: str = "工作流执行已启动"
