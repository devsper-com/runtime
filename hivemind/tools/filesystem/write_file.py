"""Write content to a file."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class WriteFileTool(Tool):
    """Write text content to a file. Overwrites if the file exists."""

    name = "write_file"
    description = "Write content to a file. Creates parent dirs if needed. Overwrites existing file."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        content = kwargs.get("content")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if content is None:
            return "Error: content is required"
        if not isinstance(content, str):
            content = str(content)
        p = Path(path).resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} characters to {p}"
        except Exception as e:
            return f"Error writing file: {e}"


register(WriteFileTool())
