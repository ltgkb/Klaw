"""本地 Agent (OpenClaw / Hermes) 端点。对齐 PRD 6.4。

本地 Skills 发现、调用、健康检查 — 平台核心差异化能力。
"""

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser
from app.schemas.local_agent import (
    LocalAgentHealth,
    ToolCallRequest,
    ToolCallResponse,
    ToolInfo,
)
from app.services import local_agent_service

router = APIRouter(prefix="/local-agent", tags=["本地 Agent"])


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools(current_user: CurrentUser):
    """发现/刷新本地 Skills 工具列表。

    来源: 本地 Skills 目录 (skill.json) + OpenClaw gateway 在线工具。
    """
    return await local_agent_service.discover_tools()


@router.post("/tools/{tool_id}/call", response_model=ToolCallResponse)
async def call_tool(
    tool_id: str,
    data: ToolCallRequest,
    current_user: CurrentUser,
):
    """调用本地工具 (Skill)。

    通过 OpenClaw gateway 调用；不可达或工具未注册时返回明确失败。
    """
    result = await local_agent_service.call_tool(tool_id, data.parameters)
    return ToolCallResponse(**result)


@router.get("/health", response_model=LocalAgentHealth)
async def health(current_user: CurrentUser):
    """本地 Agent (OpenClaw / Hermes) 健康检查。"""
    return LocalAgentHealth(**(await local_agent_service.health()))
