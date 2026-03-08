"""
Tool registry: register, get, and list tools by name.

Tools register themselves when their module is imported (see each category __init__.py).
"""

from hivemind.tools.base import Tool

_tools: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """Register a tool by name. Overwrites if the name already exists."""
    _tools[tool.name] = tool


def get(name: str) -> Tool | None:
    """Return the tool with the given name, or None if not found."""
    return _tools.get(name)


def list_tools() -> list[Tool]:
    """Return all registered tools."""
    return list(_tools.values())
