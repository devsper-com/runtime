"""Get file metadata (size, mtime, etc.)."""

from pathlib import Path
from datetime import datetime, timezone

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class FileMetadataTool(Tool):
    """Return metadata for a file: size, modification time, and whether it is a file/dir."""

    name = "file_metadata"
    description = "Get file metadata: size in bytes, modification time, type."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path to the file or directory"}},
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        p = Path(path)
        if not p.exists():
            return f"Error: path not found: {path}"
        try:
            st = p.stat()
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            kind = "directory" if p.is_dir() else "file"
            size = st.st_size if p.is_file() else 0
            return f"path: {path}\ntype: {kind}\nsize: {size} bytes\nmtime: {mtime}"
        except Exception as e:
            return f"Error: {e}"


register(FileMetadataTool())
