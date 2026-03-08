"""Preview the first N lines or bytes of a file."""

from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class FilePreviewTool(Tool):
    """Return the first N lines (default 20) or first N bytes of a file."""

    name = "file_preview"
    description = "Preview the start of a file: first N lines or first N bytes."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "lines": {"type": "integer", "description": "Number of lines to show (default 20). Ignored if bytes is set."},
            "bytes": {"type": "integer", "description": "If set, show first N bytes instead of lines"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        lines = kwargs.get("lines", 20)
        bytes_limit = kwargs.get("bytes")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(lines, int) or lines < 1:
            lines = 20
        p = Path(path)
        if not p.exists():
            return f"Error: file not found: {path}"
        if not p.is_file():
            return f"Error: not a file: {path}"
        try:
            if bytes_limit is not None:
                if not isinstance(bytes_limit, int) or bytes_limit < 1:
                    return "Error: bytes must be a positive integer"
                data = p.read_bytes()[:bytes_limit]
                return data.decode("utf-8", errors="replace")
            with p.open(encoding="utf-8", errors="replace") as f:
                out = []
                for _ in range(lines):
                    line = f.readline()
                    if not line:
                        break
                    out.append(line.rstrip("\n"))
                return "\n".join(out)
        except Exception as e:
            return f"Error: {e}"


register(FilePreviewTool())
