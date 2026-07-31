"""User-scoped remote MCP connections using the Streamable HTTP transport."""

import json
import logging
import uuid
from typing import Any

import httpx
from sqlalchemy.orm.attributes import flag_modified

from app.models.user import User
from app.utils.crypto import decrypt, encrypt
from common.ssrf_guard import assert_url_is_safe, pin_dns_global

logger = logging.getLogger("claw.mcp")

_CONFIG_KEY = "mcp_servers"
_PROTOCOL_VERSION = "2025-03-26"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_TOOLS = 200


def _servers(user: User) -> list[dict]:
    config = user.openclaw_config or {}
    value = config.get(_CONFIG_KEY, [])
    return [dict(item) for item in value if isinstance(item, dict)]


def _public_server(server: dict) -> dict:
    return {
        "id": server["id"],
        "name": server["name"],
        "url": server["url"],
        "has_token": bool(server.get("token")),
        "enabled": bool(server.get("enabled", True)),
        "tools": list(server.get("tools") or []),
    }


def list_servers(user: User) -> list[dict]:
    return [_public_server(server) for server in _servers(user)]


def cached_tools(user: User) -> list[dict]:
    tools: list[dict] = []
    for server in _servers(user):
        if not server.get("enabled", True):
            continue
        for tool in server.get("tools") or []:
            tools.append({
                "id": f"mcp:{server['id']}:{tool['name']}",
                "name": f"{server['name']} / {tool['name']}",
                "description": tool.get("description"),
                "source": "mcp",
                "parameters": tool.get("inputSchema") or {"type": "object"},
                "executable": True,
            })
    return tools


def _parse_rpc_response(response: httpx.Response) -> dict:
    if response.status_code >= 400:
        raise RuntimeError(f"MCP server returned HTTP {response.status_code}")
    if not response.content:
        return {}
    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise RuntimeError("MCP response exceeded the 2 MB safety limit")
    content_type = response.headers.get("content-type", "").lower()
    if "text/event-stream" in content_type:
        payloads = []
        for line in response.text.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw:
                    payloads.append(json.loads(raw))
        if not payloads:
            raise RuntimeError("MCP server returned an empty event stream")
        data = payloads[-1]
    else:
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("MCP server returned an invalid JSON-RPC response")
    if data.get("error"):
        error = data["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(f"MCP error: {message}")
    return data


async def _post_rpc(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    method: str,
    params: dict | None,
    request_id: int | None,
) -> tuple[dict, str | None]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params
    response = await client.post(url, headers=headers, json=payload)
    session_id = response.headers.get("mcp-session-id")
    return _parse_rpc_response(response), session_id


async def _open_and_request(server: dict, method: str, params: dict | None = None) -> dict:
    url = str(server["url"])
    hostname, resolved_ip = assert_url_is_safe(url)
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": _PROTOCOL_VERSION,
    }
    if server.get("token"):
        headers["Authorization"] = f"Bearer {decrypt(server['token'])}"

    with pin_dns_global(hostname, resolved_ip):
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            initialized, session_id = await _post_rpc(
                client,
                url,
                headers,
                "initialize",
                {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "KAI Knowledge", "version": "1.0"},
                },
                1,
            )
            if session_id:
                headers["Mcp-Session-Id"] = session_id
            await _post_rpc(client, url, headers, "notifications/initialized", None, None)
            result, _ = await _post_rpc(client, url, headers, method, params, 2)

    result["_initialize"] = initialized.get("result", {})
    return result


async def inspect_server(server: dict) -> dict:
    response = await _open_and_request(server, "tools/list", {})
    result = response.get("result") or {}
    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(tools, list):
        raise RuntimeError("MCP server did not return a tools list")
    cleaned = []
    for tool in tools[:_MAX_TOOLS]:
        if isinstance(tool, dict) and str(tool.get("name") or "").strip():
            cleaned.append({
                "name": str(tool["name"])[:200],
                "description": str(tool.get("description") or "")[:2000] or None,
                "inputSchema": tool.get("inputSchema") or {"type": "object"},
            })
    initialize = response.get("_initialize") or {}
    return {
        "tools": cleaned,
        "protocol_version": initialize.get("protocolVersion", _PROTOCOL_VERSION),
        "server_info": initialize.get("serverInfo") or {},
    }


async def create_server(db, user: User, name: str, url: str, bearer_token: str | None) -> dict:
    server = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "url": url.strip(),
        "token": encrypt(bearer_token.strip()) if bearer_token and bearer_token.strip() else "",
        "enabled": True,
    }
    inspection = await inspect_server(server)
    server["tools"] = inspection["tools"]
    config = dict(user.openclaw_config or {})
    config[_CONFIG_KEY] = [*_servers(user), server]
    user.openclaw_config = config
    flag_modified(user, "openclaw_config")
    await db.commit()
    await db.refresh(user)
    return _public_server(server)


async def refresh_server(db, user: User, server_id: uuid.UUID) -> tuple[dict, dict]:
    servers = _servers(user)
    target = next((server for server in servers if server.get("id") == str(server_id)), None)
    if target is None:
        raise ValueError("MCP 连接不存在")
    inspection = await inspect_server(target)
    target["tools"] = inspection["tools"]
    config = dict(user.openclaw_config or {})
    config[_CONFIG_KEY] = servers
    user.openclaw_config = config
    flag_modified(user, "openclaw_config")
    await db.commit()
    return _public_server(target), inspection


async def delete_server(db, user: User, server_id: uuid.UUID) -> None:
    servers = _servers(user)
    remaining = [server for server in servers if server.get("id") != str(server_id)]
    if len(remaining) == len(servers):
        raise ValueError("MCP 连接不存在")
    config = dict(user.openclaw_config or {})
    config[_CONFIG_KEY] = remaining
    user.openclaw_config = config
    flag_modified(user, "openclaw_config")
    await db.commit()


async def call_server_tool(user: User, composite_tool_id: str, parameters: dict) -> dict:
    try:
        _, server_id, tool_name = composite_tool_id.split(":", 2)
    except ValueError as exc:
        raise ValueError("MCP 工具 ID 无效") from exc
    server = next((item for item in _servers(user) if item.get("id") == server_id), None)
    if server is None or not server.get("enabled", True):
        raise ValueError("MCP 连接不存在或已停用")
    allowed = {tool.get("name") for tool in server.get("tools") or []}
    if tool_name not in allowed:
        raise ValueError("MCP 工具未在服务器清单中注册")
    response = await _open_and_request(
        server,
        "tools/call",
        {"name": tool_name, "arguments": parameters},
    )
    return response.get("result")
