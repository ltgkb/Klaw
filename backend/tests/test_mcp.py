"""Remote MCP connection management and tool discovery tests."""

import pytest


async def _register_and_login(client, email="mcp@test.com"):
    password = "secret123"
    await client.post("/api/v1/auth/register", json={
        "email": email, "name": "MCP User", "password": password,
    })
    response = await client.post("/api/v1/auth/login", json={
        "email": email, "password": password,
    })
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def mock_mcp(monkeypatch):
    async def inspect_server(server):
        return {
            "protocol_version": "2025-03-26",
            "server_info": {"name": "Demo MCP", "version": "1.0"},
            "tools": [{
                "name": "lookup",
                "description": "Look up a record",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            }],
        }

    async def call_server_tool(user, tool_id, parameters):
        return {"content": [{"type": "text", "text": parameters.get("query", "")}]}

    monkeypatch.setattr("app.services.mcp_service.inspect_server", inspect_server)
    monkeypatch.setattr("app.services.mcp_service.call_server_tool", call_server_tool)


@pytest.mark.asyncio
async def test_mcp_connection_discovery_call_and_delete(client, mock_mcp):
    headers = await _register_and_login(client)
    created = await client.post(
        "/api/v1/local-agent/mcp/servers",
        headers=headers,
        json={
            "name": "Demo MCP",
            "url": "https://mcp.example.com/mcp",
            "bearer_token": "private-token",
        },
    )
    assert created.status_code == 201
    server = created.json()
    assert server["has_token"] is True
    assert "bearer_token" not in server
    assert [tool["name"] for tool in server["tools"]] == ["lookup"]

    listed = await client.get("/api/v1/local-agent/mcp/servers", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    tools = (await client.get("/api/v1/local-agent/tools", headers=headers)).json()
    mcp_tool = next(tool for tool in tools if tool["source"] == "mcp")
    assert mcp_tool["name"] == "Demo MCP / lookup"
    assert mcp_tool["executable"] is True

    called = await client.post(
        f"/api/v1/local-agent/tools/{mcp_tool['id']}/call",
        headers=headers,
        json={"parameters": {"query": "KAI"}},
    )
    assert called.status_code == 200
    assert called.json()["success"] is True
    assert called.json()["source"] == "mcp"

    tested = await client.post(
        f"/api/v1/local-agent/mcp/servers/{server['id']}/test",
        headers=headers,
    )
    assert tested.status_code == 200
    assert tested.json()["protocol_version"] == "2025-03-26"

    deleted = await client.delete(
        f"/api/v1/local-agent/mcp/servers/{server['id']}",
        headers=headers,
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/local-agent/mcp/servers", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_mcp_connections_are_user_scoped(client, mock_mcp):
    owner_headers = await _register_and_login(client, "mcp-owner@test.com")
    other_headers = await _register_and_login(client, "mcp-other@test.com")
    await client.post(
        "/api/v1/local-agent/mcp/servers",
        headers=owner_headers,
        json={"name": "Owner MCP", "url": "https://mcp.example.com/mcp"},
    )
    response = await client.get("/api/v1/local-agent/mcp/servers", headers=other_headers)
    assert response.status_code == 200
    assert response.json() == []
