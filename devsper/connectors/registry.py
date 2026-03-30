from __future__ import annotations

from typing import Optional

from devsper.connectors.base import Connector

_connectors: dict[str, Connector] = {}


def register_connector(connector: Connector) -> None:
    """Register a connector instance by name."""

    _connectors[connector.name] = connector


def get_connector(name: str) -> Optional[Connector]:
    """Fetch a connector by name."""

    return _connectors.get(name)


def get_default_connector() -> Connector:
    """
    Get a default connector for tool execution when none is specified.
    """

    if not _connectors:
        # Lazy import of built-in connectors
        from devsper.connectors.sample_connector import LocalToolsConnector

        register_connector(LocalToolsConnector())

    # Deterministic pick: first insertion order.
    return next(iter(_connectors.values()))


def get_connector_for_tool(tool_name: str) -> Connector:
    """
    Resolve which connector should handle a tool.

    Minimal slice: return default connector for now.
    """

    _ = tool_name
    return get_default_connector()

