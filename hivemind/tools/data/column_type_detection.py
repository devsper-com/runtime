"""Detect column types (numeric, string, etc.) for a CSV. Works with stdlib or pandas."""

import csv
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ColumnTypeDetectionTool(Tool):
    """Infer column types from a CSV: int, float, or str based on sample rows."""

    name = "column_type_detection"
    description = "Detect column types (int, float, str) from a CSV file."
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
            data = rows[1:][:100]
            result = []
            for col_idx, col_name in enumerate(header):
                values = [row[col_idx] if col_idx < len(row) else "" for row in data]
                types = []
                for v in values:
                    v = (v or "").strip()
                    if not v:
                        continue
                    try:
                        int(v)
                        types.append("int")
                    except ValueError:
                        try:
                            float(v)
                            types.append("float")
                        except ValueError:
                            types.append("str")
                inferred = "str"
                if all(t == "int" for t in types):
                    inferred = "int"
                elif types and "str" not in types:
                    inferred = "float"
                result.append(f"{col_name}: {inferred}")
            return "\n".join(result)
        except Exception as e:
            return f"Error: {e}"


register(ColumnTypeDetectionTool())
