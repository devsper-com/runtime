"""Tests for MCP and A2A protocol integration (v1.10.5)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- MCP ---


def test_mcp_stdio_connect():
    """Mock MCP server (HTTP): connect, list tools."""
    from devsper.tools.mcp.client import MCPClient, MCPToolDefinition
    import asyncio

    client = MCPClient("test", "http", url="http://localhost:9999")
    tools_response = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "read_file", "description": "Read a file", "inputSchema": {"type": "object"}}]}}

    async def mock_post(*args, **kwargs):
        class Resp:
            def raise_for_status(self): pass
            def json(self): return tools_response
        return Resp()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client.aclose = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client
        tools = asyncio.run(client.list_tools())
    assert len(tools) == 1
    assert tools[0].name == "read_file"
    assert isinstance(tools[0], MCPToolDefinition)


def test_mcp_tool_adapter_registered():
    """Adapter appears in tool registry after discover."""
    from devsper.tools.registry import list_tools, get
    from devsper.tools.mcp.adapter import MCPToolAdapter
    from devsper.tools.mcp.client import MCPClient, MCPToolDefinition

    mock_client = MagicMock(spec=MCPClient)
    defn = MCPToolDefinition("proto_fake_tool", "Fake MCP tool", {"type": "object"})
    adapter = MCPToolAdapter("proto_test_server", defn, mock_client)
    after = list_tools()
    mcp_tools = [t for t in after if getattr(t, "category", "") == "mcp"]
    assert any(t.name == "proto_test_server.proto_fake_tool" for t in mcp_tools)
    got = get("proto_test_server.proto_fake_tool")
    assert got is not None and got.name == "proto_test_server.proto_fake_tool"


def test_mcp_tool_run():
    """adapter.run() calls client.call_tool with correct args."""
    from devsper.tools.mcp.client import MCPClient, MCPToolDefinition
    from devsper.tools.mcp.adapter import MCPToolAdapter

    mock_client = MagicMock(spec=MCPClient)
    mock_client.call_tool = AsyncMock(return_value="file contents here")
    defn = MCPToolDefinition("read_file", "Read a file", {"type": "object", "properties": {"path": {"type": "string"}}})
    adapter = MCPToolAdapter("run_test_fs", defn, mock_client)
    out = adapter.run(path="/tmp/foo.txt")
    assert out == "file contents here"
    mock_client.call_tool.assert_called_once()
    call_args = mock_client.call_tool.call_args
    assert call_args[0][0] == "read_file"
    assert call_args[0][1] == {"path": "/tmp/foo.txt"}


# --- A2A ---


def test_a2a_agent_card_fetch():
    """Mock HTTP server returns AgentCard; client parses correctly."""
    from devsper.agents.a2a.client import A2AClient, _parse_agent_card
    from devsper.agents.a2a.types import AgentCard
    import asyncio

    payload = {
        "name": "code-reviewer",
        "description": "Reviews code",
        "url": "http://localhost:8080",
        "version": "0.2.1",
        "capabilities": ["streaming"],
        "skills": [
            {"id": "review", "name": "Review", "description": "Review code", "inputModes": ["text"], "outputModes": ["text"]}
        ],
    }
    card = _parse_agent_card(payload)
    assert isinstance(card, AgentCard)
    assert card.name == "code-reviewer"
    assert len(card.skills) == 1
    assert card.skills[0].id == "review"

    # Also test via client.get_agent_card with mocked httpx
    async def mock_get(url, **kwargs):
        class Resp:
            def raise_for_status(self): pass
            def json(self): return payload
        return Resp()

    client = A2AClient()
    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=mock_get)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_http
        card2 = asyncio.run(client.get_agent_card("http://localhost:8080"))
    assert card2.name == "code-reviewer"


def test_a2a_task_send_and_poll():
    """Send task; mock server returns completed; response parsed."""
    from devsper.agents.a2a.client import A2AClient
    from devsper.agents.a2a.types import A2ATaskRequest
    import asyncio

    client = A2AClient()
    request = A2ATaskRequest(id="task-1", message={"text": "Review this code"})
    completed = {"id": "task-1", "status": "completed", "result": "Looks good.", "artifacts": []}

    async def mock_post(url, **kwargs):
        class Resp:
            def raise_for_status(self): pass
            def json(self): return completed
        return Resp()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=mock_post)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client
        resp = asyncio.run(client.send_task("http://localhost:8080", request))
    assert resp.status == "completed"
    assert resp.result == "Looks good."


def test_a2a_tool_adapter_registered():
    """A2AAgentTool in registry after discovery."""
    from devsper.agents.a2a.types import AgentSkill
    from devsper.agents.a2a.tool_adapter import A2AAgentTool
    from devsper.tools.registry import list_tools

    skill = AgentSkill("proto_review", "Review", "Review code", ["text"], ["text"])
    A2AAgentTool("proto_code_reviewer", skill, "http://localhost:8080")
    all_tools = list_tools()
    a2a_tools = [t for t in all_tools if getattr(t, "category", "") == "a2a"]
    assert any(t.name == "proto_code_reviewer.proto_review" for t in a2a_tools)


def test_a2a_server_agent_card_endpoint():
    """GET /.well-known/agent.json returns valid AgentCard."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from devsper.agents.a2a.server import create_a2a_app

    app = create_a2a_app(host="localhost", port=8080, swarm_name="test-swarm")
    client = TestClient(app)
    r = client.get("/.well-known/agent.json")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "test-swarm"
    assert "skills" in data
    assert "streaming" in data["capabilities"]


def test_a2a_server_task_endpoint():
    """POST /tasks/send runs swarm, returns result."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from devsper.agents.a2a.server import create_a2a_app

    app = create_a2a_app(host="localhost", port=8080, swarm_name="devsper")
    client = TestClient(app)
    with patch("devsper.swarm.swarm.Swarm") as mock_swarm:
        mock_swarm.return_value.run.return_value = {"root": "Done."}
        r = client.post("/tasks/send", json={"id": "t1", "message": {"text": "Hello"}})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert "Done." in (data.get("result") or "")
