from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConnectorToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    category: str


@dataclass(frozen=True)
class ConnectorAuth:
    """
    Auth context resolved by the connector (tokens, keys, etc).

    Connectors may choose to inject this into tool args (preferred for local tools)
    or to set environment variables before execution.
    """

    values: dict[str, Any]


class Connector(ABC):
    """Composio-like connector interface (runtime-only)."""

    # Stable connector identifier (e.g. "composio:google", "runtime:local")
    name: str

    @abstractmethod
    def list_tools(self) -> list[ConnectorToolSchema]:
        """Return the tool inventory exposed by this connector."""

    @abstractmethod
    def resolve_auth(self, tool_name: str, tool_args: dict[str, Any] | None = None) -> ConnectorAuth:
        """Resolve connector-specific auth context for tool execution."""

    @abstractmethod
    def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        task_type: str | None = None,
    ) -> str:
        """Execute the tool and return its string output."""

    def should_sandbox_tool(self, tool_name: str) -> bool:
        """
        Optional sandbox hint. The runtime AgentSandbox can enforce quotas, but the
        connector can still mark risky tools for stricter handling.
        """

        return False

