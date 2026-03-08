"""Read contents of a file from the filesystem."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ReadFileTool(Tool):
    """Read and return the full text content of a file."""

    name = "read_file"
    description = "Read the contents of a file. Returns the raw text."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path to the file"}},
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        p = Path(path)
        if not p.exists():
            return f"Error: file not found: {path}"
        if not p.is_file():
            return f"Error: not a file: {path}"
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"


register(ReadFileTool())
