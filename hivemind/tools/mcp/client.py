"""
MCP client: connect to MCP servers over stdio, HTTP, or SSE.
Implements initialize handshake, tools/list, tools/call.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any

from hivemind.protocols import MCP_PROTOCOL_VERSION
from hivemind.types.exceptions import MCPToolError


@dataclass
class MCPToolDefinition:
    """One tool as returned by MCP tools/list."""
    name: str
    description: str
    input_schema: dict  # JSON Schema as returned by MCP server


def _next_id() -> int:
    """Simple monotonic id for JSON-RPC requests."""
    _next_id._n = getattr(_next_id, "_n", 0) + 1
    return _next_id._n


class MCPClient:
    """
    Connects to an MCP server over stdio, HTTP, or SSE transport.
    Implements MCP protocol: initialize handshake, tools/list, tools/call.
    """

    def __init__(
        self,
        name: str,
        transport: str,
        *,
        command: list[str] | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: int = 30,
        auto_reconnect: bool = True,
    ) -> None:
        self.name = name
        self.transport = transport
        self.command = command or []
        self.url = (url or "").rstrip("/")
        self.env = dict(env or {})
        self.timeout_seconds = timeout_seconds
        self.auto_reconnect = auto_reconnect
        self._server_capabilities: dict[str, Any] = {}
        self._stdio_process: asyncio.subprocess.Process | None = None
        self._stdio_reader: asyncio.StreamReader | None = None
        self._stdio_writer: asyncio.StreamWriter | None = None
        self._connected = False

    async def connect(self) -> None:
        """Send initialize request, await initialized notification, cache server capabilities."""
        if self.transport == "stdio":
            await self._connect_stdio()
        elif self.transport in ("http", "sse"):
            await self._connect_http_sse()
        else:
            raise ValueError(f"Unsupported MCP transport: {self.transport}")

        req = {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "hivemind", "version": "1.10.5"},
            },
        }
        resp = await self._request(req)
        if "result" in resp:
            self._server_capabilities = resp["result"].get("capabilities", {})
        # Send initialized notification (no response expected)
        await self._send_notification("notifications/initialized", {})
        self._connected = True

    async def _connect_stdio(self) -> None:
        if not self.command:
            raise ValueError("stdio transport requires command")
        env = os.environ.copy()
        env.update(self.env)
        self._stdio_process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
        )
        assert self._stdio_process.stdin and self._stdio_process.stdout
        self._stdio_reader = self._stdio_process.stdout
        self._stdio_writer = self._stdio_process.stdin

    async def _connect_http_sse(self) -> None:
        if not self.url:
            raise ValueError("http/sse transport requires url")
        # HTTP: no persistent connection for initialize; we'll use POST per request
        self._connected = True

    def _get_http_client(self):
        import httpx
        return httpx.AsyncClient(timeout=float(self.timeout_seconds))  # type: ignore[return-value]

    async def _request(self, req: dict) -> dict:
        if self.transport == "stdio":
            return await self._request_stdio(req)
        return await self._request_http(req)

    async def _request_stdio(self, req: dict) -> dict:
        if not self._stdio_writer or not self._stdio_reader:
            raise RuntimeError("stdio not connected")
        msg = json.dumps(req) + "\n"
        self._stdio_writer.write(msg.encode("utf-8"))
        await self._stdio_writer.drain()
        line = await asyncio.wait_for(
            self._stdio_reader.readline(),
            timeout=self.timeout_seconds,
        )
        if not line:
            raise ConnectionError("MCP server closed stdin")
        data = json.loads(line.decode("utf-8").strip())
        if "error" in data:
            raise MCPToolError(data["error"].get("message", str(data["error"])))
        return data

    async def _request_http(self, req: dict) -> dict:
        import httpx
        client = self._get_http_client()
        try:
            # MCP over HTTP: POST JSON-RPC to endpoint
            endpoint = self.url if self.url.endswith("/") else f"{self.url}/"
            r = await client.post(endpoint, json=req)
            r.raise_for_status()
            out = r.json()
            if "error" in out:
                raise MCPToolError(out["error"].get("message", str(out["error"])))
            return out
        except httpx.HTTPError as e:
            raise MCPToolError(str(e))
        finally:
            await client.aclose()

    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a notification (no id, no response)."""
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if self.transport == "stdio" and self._stdio_writer:
            self._stdio_writer.write((json.dumps(msg) + "\n").encode("utf-8"))
            await self._stdio_writer.drain()
        elif self.transport in ("http", "sse"):
            async with self._get_http_client() as client:
                await client.post(
                    self.url if self.url.endswith("/") else f"{self.url}/",
                    json=msg,
                )

    async def list_tools(self) -> list[MCPToolDefinition]:
        """Send tools/list request; return list of MCPToolDefinition."""
        req = {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/list",
            "params": {},
        }
        resp = await self._request(req)
        result = resp.get("result") or {}
        tools_data = result.get("tools", [])
        return [
            MCPToolDefinition(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Send tools/call request; extract text from result.content; on error raise MCPToolError."""
        req = {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        resp = await self._request(req)
        result = resp.get("result")
        if result is None:
            raise MCPToolError(resp.get("error", {}).get("message", "Unknown error"))
        if result.get("isError"):
            content = result.get("content", [])
            parts = [
                c.get("text", str(c))
                for c in content
                if isinstance(c, dict)
            ]
            raise MCPToolError("\n".join(parts) if parts else "Tool returned error")
        content = result.get("content") or []
        texts = [
            c.get("text", "") if isinstance(c, dict) else str(c)
            for c in content
        ]
        return "\n".join(texts)

    async def disconnect(self) -> None:
        """Close connection."""
        if self.transport == "stdio" and self._stdio_writer:
            try:
                self._stdio_writer.close()
                await self._stdio_writer.wait_closed()
            except Exception:
                pass
            self._stdio_writer = None
            self._stdio_reader = None
        if self._stdio_process and self._stdio_process.returncode is None:
            self._stdio_process.terminate()
            try:
                await asyncio.wait_for(self._stdio_process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._stdio_process.kill()
            self._stdio_process = None
        self._connected = False

    async def reconnect(self) -> None:
        """Disconnect and connect again."""
        await self.disconnect()
        await self.connect()


