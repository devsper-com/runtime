from __future__ import annotations

import os
from typing import Any

from devsper.connectors.base import Connector, ConnectorAuth, ConnectorToolSchema
from devsper.tools.registry import get_with_mcp_fallback, list_tools as list_all_tools
from devsper.tools.tool_runner import run_tool


class LocalToolsConnector(Connector):
    """
    Sample runtime-only connector that exposes the local devsper tool registry.

    It demonstrates the Composio-like shape:
    - tool inventory (list_tools)
    - auth resolution (resolve_auth via env vars)
    - execution using the existing tool runner (execute_tool)
    """

    name = "runtime:local"

    def list_tools(self) -> list[ConnectorToolSchema]:
        tools = list_all_tools()
        out: list[ConnectorToolSchema] = []
        for t in tools:
            out.append(
                ConnectorToolSchema(
                    name=t.name,
                    description=getattr(t, "description", "") or "",
                    input_schema=getattr(t, "input_schema", {}) or {},
                    output_schema=getattr(t, "output_schema", {}) or {},
                    category=getattr(t, "category", "") or "general",
                )
            )
        return out

    def resolve_auth(
        self, tool_name: str, tool_args: dict[str, Any] | None = None
    ) -> ConnectorAuth:
        _ = (tool_name, tool_args)

        # Minimal token retrieval hook. Tools may ignore this if they don't need it.
        token = (
            os.environ.get("DEVSPER_CONNECTOR_TOKEN")
            or os.environ.get("DEVSPER_LOCALCONNECTOR_TOKEN")
            or os.environ.get("DEVSPER_LOCAL_CONNECTOR_TOKEN")
        )
        if not token:
            return ConnectorAuth(values={})
        return ConnectorAuth(values={"token": token})

    def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        task_type: str | None = None,
    ) -> str:
        auth = self.resolve_auth(tool_name, tool_args)
        token = auth.values.get("token")

        # Inject the token only if the target tool's schema asks for a compatible field.
        # This keeps local execution safe and schema-valid.
        tool = get_with_mcp_fallback(tool_name)
        if tool is not None and token:
            props = tool.input_schema.get("properties", {}) if hasattr(tool, "input_schema") else {}
            augmented = dict(tool_args)
            for key in ("token", "api_key", "access_token", "bearer_token"):
                if key in props and key not in augmented:
                    augmented[key] = token
            tool_args = augmented

        return run_tool(tool_name, tool_args, task_type=task_type)

