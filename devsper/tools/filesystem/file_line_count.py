"""Count lines in a text file."""

from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class FileLineCountTool(Tool):
    """Count the number of lines in a text file."""

    name = "file_line_count"
    description = "Count lines in a file. Uses universal newlines."
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
            count = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
            return str(count)
        except Exception as e:
            return f"Error: {e}"


register(FileLineCountTool())
