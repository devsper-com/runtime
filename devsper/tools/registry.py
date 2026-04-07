"""
Tool registry: register, get, and list tools by name.

Tools register themselves when their module is imported (see each category __init__.py).
"""

from devsper.core.tools.registry import ToolRegistry as CoreToolRegistry
from devsper.core.tools.registry import get_global_registry
from devsper.tools.base import Tool, ToolStub


def register(tool: Tool) -> None:
    """Register a tool by name. Overwrites if the name already exists."""
    get_global_registry().register(tool)


def get(name: str) -> Tool | None:
    """Return the tool with the given name, or None if not found."""
    return get_global_registry().get(name)


def get_with_mcp_fallback(name: str) -> Tool | None:
    """
    Return the tool by name. If not found and name has no dot (e.g. 'list_dir'),
    look for a single MCP-style tool whose name ends with '.' + name (e.g. 'filesystem.list_dir').
    Lets agents use short names when only one such MCP tool is registered.
    """
    return get_global_registry().get_with_suffix_fallback(name)


def list_tools() -> list[Tool]:
    """Return all registered tools."""
    return get_global_registry().list_tools()


def deregister(name: str) -> None:
    """Remove a tool by name. No-op if the tool is not registered."""
    reg = get_global_registry()
    with reg._lock:
        reg._tools.pop(name, None)


def clear() -> None:
    """Clear all registered tools (used when rebuilding registry from bus payload)."""
    get_global_registry().clear()


class ToolRegistry:
    """
    Serializable view of the currently registered tools.
    Used to transport tool inventory from controller -> workers in distributed mode.
    """

    def __init__(self) -> None:
        self._tools: CoreToolRegistry = CoreToolRegistry()

    def register(self, tool: Tool) -> None:
        self._tools.register(tool)

    def list(self) -> list[Tool]:
        return self._tools.list_tools()

    def to_dict(self) -> dict:
        """Serialize all registered tools for transport over bus."""
        return {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": getattr(tool, "category", "general") or "general",
                    "input_schema": getattr(tool, "input_schema", {}) or {},
                    "output_schema": getattr(tool, "output_schema", {}) or {},
                    "class_path": f"{tool.__class__.__module__}.{tool.__class__.__qualname__}",
                }
                for tool in self._tools.list_tools()
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolRegistry":
        """
        Reconstruct registry on worker side.
        Attempts to import and instantiate each tool class.
        Falls back to ToolStub for tools whose class isn't importable.
        """
        import importlib

        registry = cls()
        for t in data.get("tools", []) or []:
            try:
                module_path, class_name = str(t["class_path"]).rsplit(".", 1)
                module = importlib.import_module(module_path)
                tool_cls = getattr(module, class_name)
                registry.register(tool_cls())
            except Exception:
                stub = ToolStub(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    category=t.get("category", "general") or "general",
                    input_schema=t.get("input_schema", {}) or {},
                )
                registry.register(stub)
        return registry

    @classmethod
    def from_global(cls) -> "ToolRegistry":
        """Snapshot the current process-wide tool registry into a serializable ToolRegistry."""
        r = cls()
        for t in list_tools():
            r.register(t)
        return r

    def install_global(self) -> None:
        """Replace process-wide registry with this registry."""
        clear()
        for t in self._tools.list_tools():
            register(t)
