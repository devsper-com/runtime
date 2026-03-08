"""Append content to a file."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class AppendFileTool(Tool):
    """Append text to the end of a file. Creates the file if it does not exist."""

    name = "append_file"
    description = "Append content to a file. Creates file if it does not exist."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "content": {"type": "string", "description": "Content to append"},
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
        p = Path(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(content)
            return f"Appended {len(content)} characters to {path}"
        except Exception as e:
            return f"Error appending to file: {e}"


register(AppendFileTool())
