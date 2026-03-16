"""
MCP (Model Context Protocol) integration: client, tool adapter, discovery.
"""

from devsper.config.schema import MCPServerConfig
from devsper.tools.mcp.client import (
    MCPClient,
    MCPToolDefinition,
)
from devsper.tools.mcp.adapter import MCPToolAdapter
from devsper.tools.mcp.discovery import (
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
