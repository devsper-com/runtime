"""Report missing/empty values per column in a CSV."""

import csv
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class MissingValueReportTool(Tool):
    """Count missing or empty values per column in a CSV."""

    name = "missing_value_report"
    description = "Report count of missing/empty values per column in a CSV."
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
            data = rows[1:]
            n_rows = len(data)
            lines = [f"Total rows: {n_rows}", ""]
            for col_idx, col_name in enumerate(header):
                missing = sum(1 for row in data if col_idx >= len(row) or (row[col_idx] or "").strip() == "")
                pct = (100 * missing / n_rows) if n_rows else 0
                lines.append(f"{col_name}: {missing} missing ({pct:.1f}%)")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


register(MissingValueReportTool())
