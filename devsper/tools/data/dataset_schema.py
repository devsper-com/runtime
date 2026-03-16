"""Describe CSV schema: column names and sample value types."""

import csv
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DatasetSchemaTool(Tool):
    """Return CSV schema: column names and a one-line description (from first row)."""

    name = "dataset_schema"
    description = "Describe CSV schema: column names and example types."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path to CSV file"}},
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        p = Path(path)
        if not p.exists() or not p.is_file():
            return f"Error: file not found: {path}"
        try:
            with p.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if not rows:
                return "Empty CSV."
            header = rows[0]
            sample = rows[1] if len(rows) > 1 else []
            lines = [f"Columns: {len(header)}", ""]
            for i, name in enumerate(header):
                ex = sample[i] if i < len(sample) else ""
                lines.append(f"  {name}: example = {repr(ex)[:50]}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


register(DatasetSchemaTool())
