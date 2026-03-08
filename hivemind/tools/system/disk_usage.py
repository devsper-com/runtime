"""Report disk usage for a path. Uses stdlib shutil."""

import shutil
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class DiskUsageTool(Tool):
    """Return disk usage for a path: total, used, free (in bytes)."""

    name = "disk_usage"
    description = "Get disk usage for a path. Returns total, used, free in bytes."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path (default: current dir)"}},
        "required": [],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path", ".")
        if path is not None and not isinstance(path, str):
            return "Error: path must be a string"
        p = Path(path or ".").resolve()
        if not p.exists():
            return f"Error: path not found: {p}"
        try:
            usage = shutil.disk_usage(p)
            return f"total = {usage.total} bytes\nused = {usage.used} bytes\nfree = {usage.free} bytes"
        except Exception as e:
            return f"Error: {e}"


register(DiskUsageTool())
