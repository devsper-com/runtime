"""
MCPToolAdapter: wrap an MCP tool as a hivemind Tool for the tool registry.
"""

import asyncio

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

from hivemind.tools.mcp.client import MCPClient, MCPToolDefinition


class MCPToolAdapter(Tool):
    """
    Wraps an MCPToolDefinition as a hivemind Tool so it appears in the
    existing tool registry and selection pipeline unchanged.
    """

    def __init__(
        self,
        server_name: str,
        definition: MCPToolDefinition,
        client: MCPClient,
    ) -> None:
        # "{server_name}.{tool_name}" to avoid collisions
        self.name = f"{server_name}.{definition.name}"
        self.description = definition.description or f"MCP tool: {definition.name}"
        self.category = "mcp"
        self.input_schema = definition.input_schema
        self._client = client
        self._mcp_tool_name = definition.name
        # Register in tool registry on adapter creation
        register(self)

    def run(self, **kwargs) -> str:
        """Execute the MCP tool via client.call_tool; sync wrapper around async."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        if loop.is_running():
            # If we're already inside an async context, run in a new loop (e.g. sync call from sync code)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    asyncio.run,
                    self._client.call_tool(self._mcp_tool_name, kwargs),
                )
                return future.result()
        return loop.run_until_complete(
            self._client.call_tool(self._mcp_tool_name, kwargs)
        )
