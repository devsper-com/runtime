"""
MCP discovery: connect to server, list tools, wrap as MCPToolAdapter and optionally register.
"""

from hivemind.config.schema import MCPServerConfig
from hivemind.tools.mcp.client import MCPClient, MCPToolDefinition
from hivemind.tools.mcp.adapter import MCPToolAdapter


def _config_to_client(config: MCPServerConfig) -> MCPClient:
    """Build MCPClient from config model."""
    return MCPClient(
        name=config.name,
        transport=config.transport,
        command=config.command,
        url=config.url,
        env=config.env,
        timeout_seconds=config.timeout_seconds,
        auto_reconnect=config.auto_reconnect,
    )


async def discover_mcp_tools_async(server_config: MCPServerConfig) -> list[MCPToolAdapter]:
    """Connect client, list tools, wrap each as MCPToolAdapter, return list."""
    client = _config_to_client(server_config)
    await client.connect()
    definitions = await client.list_tools()
    adapters = [
        MCPToolAdapter(server_config.name, defn, client)
        for defn in definitions
    ]
    return adapters


def discover_mcp_tools(server_config: MCPServerConfig) -> list[MCPToolAdapter]:
    """Synchronous wrapper: connect, list tools, wrap as MCPToolAdapter."""
    import asyncio
    return asyncio.run(discover_mcp_tools_async(server_config))


async def register_mcp_server_async(server_config: MCPServerConfig) -> int:
    """Call discover_mcp_tools, register each adapter in tool registry. Return count."""
    adapters = await discover_mcp_tools_async(server_config)
    return len(adapters)


def register_mcp_server(server_config: MCPServerConfig) -> int:
    """Synchronous: discover and register MCP tools; return count registered."""
    import asyncio
    return asyncio.run(register_mcp_server_async(server_config))
