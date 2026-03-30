from __future__ import annotations

import csv
import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.storage.uploads import resolve_upload


def _summarize_csv(path: Path, max_rows: int = 20) -> str:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            rows.append(row)
    return json.dumps(
        {
            "path": str(path),
            "columns": list(rows[0].keys()) if rows else [],
            "sample_rows": rows,
            "row_count_sampled": len(rows),
        }
    )


class ReadCSVTool(Tool):
    name = "read_csv"
    description = "Read a CSV file from a path and return columns/sample rows."
    category = "data"
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "max_rows": {"type": "integer"}},
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = str(kwargs.get("path") or "").strip()
        max_rows = int(kwargs.get("max_rows") or 20)
        if not path:
            return "Error: path is required."
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: CSV not found: {path}"
        try:
            return _summarize_csv(p, max_rows=max_rows)
        except Exception as e:
            return f"Error: read_csv failed: {e}"


class ReadUploadedCSVTool(Tool):
    name = "read_uploaded_csv"
    description = "Read uploaded CSV by upload_id."
    category = "data"
    input_schema = {
        "type": "object",
        "properties": {"upload_id": {"type": "string"}, "max_rows": {"type": "integer"}},
        "required": ["upload_id"],
    }

    def run(self, **kwargs) -> str:
        upload_id = str(kwargs.get("upload_id") or "").strip()
        max_rows = int(kwargs.get("max_rows") or 20)
        if not upload_id:
            return "Error: upload_id is required."
        p = resolve_upload(upload_id)
        if p is None:
            return f"Error: upload not found: {upload_id}"
        try:
            return _summarize_csv(p, max_rows=max_rows)
        except Exception as e:
            return f"Error: read_uploaded_csv failed: {e}"


register(ReadCSVTool())
register(ReadUploadedCSVTool())

