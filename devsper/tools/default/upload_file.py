from __future__ import annotations

import json

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.storage.uploads import save_upload


class UploadFileTool(Tool):
    name = "upload_file"
    description = "Upload a local file into runtime storage and return upload_id."
    category = "filesystem"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Local file path"},
            "filename": {"type": "string", "description": "Optional output filename"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = str(kwargs.get("path") or "").strip()
        filename = kwargs.get("filename")
        if not path:
            return "Error: path is required."
        try:
            meta = save_upload(path, filename=str(filename) if filename else None)
            return json.dumps(meta)
        except Exception as e:
            return f"Error: upload_file failed: {e}"


register(UploadFileTool())

