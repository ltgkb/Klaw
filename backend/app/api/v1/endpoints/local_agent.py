"""本地 Agent (OpenClaw / Hermes) 端点。对齐 PRD 6.4。

本地 Skills 发现、调用、健康检查 — 平台核心差异化能力。
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser, DBSession
from app.schemas.local_agent import (
    LocalAgentHealth,
    McpServerCreate,
    McpServerRead,
    McpServerTestResponse,
    ToolCallRequest,
    ToolCallResponse,
    ToolInfo,
)
from app.services import local_agent_service, mcp_service

router = APIRouter(prefix="/local-agent", tags=["本地 Agent"])


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools(current_user: CurrentUser):
    """发现/刷新本地 Skills 工具列表。

    来源: 本地 Skills 目录 (skill.json) + OpenClaw gateway 在线工具。
    """
    return await local_agent_service.discover_tools(current_user)


@router.post("/tools/{tool_id}/call", response_model=ToolCallResponse)
async def call_tool(
    tool_id: str,
    data: ToolCallRequest,
    current_user: CurrentUser,
):
    """调用本地工具 (Skill)。

    通过 OpenClaw gateway 调用；不可达或工具未注册时返回明确失败。
    """
    result = await local_agent_service.call_tool(tool_id, data.parameters, current_user)
    return ToolCallResponse(**result)


@router.get("/health", response_model=LocalAgentHealth)
async def health(current_user: CurrentUser):
    """本地 Agent (OpenClaw / Hermes) 健康检查。"""
    return LocalAgentHealth(**(await local_agent_service.health()))


@router.get("/mcp/servers", response_model=list[McpServerRead])
async def list_mcp_servers(current_user: CurrentUser):
    """List the current user's saved remote MCP connections."""
    return mcp_service.list_servers(current_user)


@router.post("/mcp/servers", response_model=McpServerRead, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    data: McpServerCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Verify an MCP server, discover tools, then persist the connection."""
    try:
        return await mcp_service.create_server(
            db, current_user, data.name, data.url, data.bearer_token
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP 连接失败: {exc}",
        ) from exc


@router.post("/mcp/servers/{server_id}/test", response_model=McpServerTestResponse)
async def test_mcp_server(
    server_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """Reconnect and refresh the cached MCP tool list."""
    try:
        server, inspection = await mcp_service.refresh_server(db, current_user, server_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP 连接测试失败: {exc}",
        ) from exc
    return McpServerTestResponse(
        protocol_version=inspection["protocol_version"],
        server_info=inspection["server_info"],
        server=McpServerRead(**server),
    )


@router.delete("/mcp/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(
    server_id: uuid.UUID,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a saved MCP connection and remove its tools from discovery."""
    try:
        await mcp_service.delete_server(db, current_user, server_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
