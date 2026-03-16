"""Compute a hash of a file's contents."""

import hashlib
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class FileHashTool(Tool):
    """Compute SHA-256 hash of a file's contents."""

    name = "file_hash"
    description = "Compute SHA-256 hash of a file. Returns hex digest."
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
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception as e:
            return f"Error: {e}"


register(FileHashTool())
