"""Report distribution statistics for numeric columns: mean, std, quartiles."""

import csv
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class DatasetDistributionReportTool(Tool):
    """
    Report distribution stats for numeric columns: mean, std, min, max, quartiles.
    """

    name = "dataset_distribution_report"
    description = "Report distribution statistics for numeric columns in a dataset."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV"},
            "max_columns": {"type": "integer", "description": "Max columns to report (default 20)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_columns = kwargs.get("max_columns", 20)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_columns, int) or max_columns < 1:
            max_columns = 20
        if np is None:
            return "Error: numpy is required for this tool"
        p = Path(path).resolve()
        if not p.exists() or not p.is_file():
            return f"Error: file not found: {path}"
        try:
            with p.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if not rows:
                return "Empty CSV."
            lines = ["Distribution report", "=" * 40]
            for col in list(rows[0].keys())[:max_columns]:
                try:
                    arr = np.array([float(row.get(col, np.nan)) for row in rows], dtype=float)
                    arr = arr[~np.isnan(arr)]
                    if len(arr) < 2:
                        continue
                    lines.append(f"{col}: mean={np.mean(arr):.4f}, std={np.std(arr):.4f}, min={np.min(arr):.4f}, max={np.max(arr):.4f}, q25={np.percentile(arr, 25):.4f}, q75={np.percentile(arr, 75):.4f}")
                except (ValueError, TypeError):
                    continue
            return "\n".join(lines) if len(lines) > 1 else "No numeric columns found."
        except Exception as e:
            return f"Error: {e}"


register(DatasetDistributionReportTool())
