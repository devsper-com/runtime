"""
MCP (Model Context Protocol) integration: client, tool adapter, discovery.
"""

from hivemind.config.schema import MCPServerConfig
from hivemind.tools.mcp.client import (
    MCPClient,
    MCPToolDefinition,
)
from hivemind.tools.mcp.adapter import MCPToolAdapter
from hivemind.tools.mcp.discovery import (
    discover_mcp_tools,
    register_mcp_server,
)

__all__ = [
    "MCPClient",
    "MCPToolAdapter",
    "MCPServerConfig",
    "MCPToolDefinition",
    "discover_mcp_tools",
    "register_mcp_server",
]
