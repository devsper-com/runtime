from __future__ import annotations

import threading
from typing import Any


class ToolRegistry:
    """Thread-safe runtime tool registry with optional alias fallback."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: dict[str, Any] = {}

    def register(self, tool: Any) -> None:
        name = getattr(tool, "name", "")
        if not isinstance(name, str) or not name:
            raise ValueError("tool must define a non-empty name")
        with self._lock:
            self._tools[name] = tool

    def get(self, name: str) -> Any | None:
        with self._lock:
            return self._tools.get(name)

    def get_with_suffix_fallback(self, name: str) -> Any | None:
        out = self.get(name)
        if out is not None:
            return out
        if "." in name:
            return None
        with self._lock:
            matches = [t for n, t in self._tools.items() if n.endswith("." + name)]
        return matches[0] if len(matches) == 1 else None

    def list_tools(self) -> list[Any]:
        with self._lock:
            return list(self._tools.values())

    def clear(self) -> None:
        with self._lock:
            self._tools.clear()


_global_registry = ToolRegistry()


def get_global_registry() -> ToolRegistry:
    return _global_registry

