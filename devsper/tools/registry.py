"""
Tool registry: register, get, and list tools by name.

Tools register themselves when their module is imported (see each category __init__.py).
"""

from devsper.tools.base import Tool

_tools: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """Register a tool by name. Overwrites if the name already exists."""
    _tools[tool.name] = tool


def get(name: str) -> Tool | None:
    """Return the tool with the given name, or None if not found."""
    return _tools.get(name)


def get_with_mcp_fallback(name: str) -> Tool | None:
    """
    Return the tool by name. If not found and name has no dot (e.g. 'list_dir'),
    look for a single MCP-style tool whose name ends with '.' + name (e.g. 'filesystem.list_dir').
    Lets agents use short names when only one such MCP tool is registered.
    """
    t = _tools.get(name)
    if t is not None:
        return t
    if "." in name:
        return None
    candidates = [t for t in _tools.values() if t.name.endswith("." + name)]
    return candidates[0] if len(candidates) == 1 else None


def list_tools() -> list[Tool]:
    """Return all registered tools."""
    return list(_tools.values())
