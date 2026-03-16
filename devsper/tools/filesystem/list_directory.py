"""List contents of a directory."""

from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ListDirectoryTool(Tool):
    """List files and subdirectories in a directory."""

    name = "list_directory"
    description = "List entries in a directory. Returns names of files and subdirs."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the directory"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        p = Path(path)
        if not p.exists():
            return f"Error: path not found: {path}"
        if not p.is_dir():
            return f"Error: not a directory: {path}"
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines = [f"{'[dir] ' if e.is_dir() else ''}{e.name}" for e in entries]
            return "\n".join(lines) if lines else "(empty)"
        except Exception as e:
            return f"Error listing directory: {e}"


register(ListDirectoryTool())
