"""Summarize a CSV file: row count, column names, sample rows."""

import csv
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class CsvSummaryTool(Tool):
    """Summarize a CSV file: columns, row count, and first few rows."""

    name = "csv_summary"
    description = "Summarize a CSV file: column names, row count, and first N rows."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the CSV file"},
            "sample_rows": {"type": "integer", "description": "Number of rows to show (default 5)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        sample_rows = kwargs.get("sample_rows", 5)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(sample_rows, int) or sample_rows < 1:
            sample_rows = 5
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
            n = len(data)
            sample = data[:sample_rows]
            lines = [f"Columns: {', '.join(header)}", f"Row count: {n}", "Sample:"]
            for i, row in enumerate(sample, 1):
                lines.append(f"  {i}: {row}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


register(CsvSummaryTool())
