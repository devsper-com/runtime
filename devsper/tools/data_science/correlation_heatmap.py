"""Compute pairwise correlation matrix for numeric columns and return as text table."""

import csv
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class CorrelationHeatmapTool(Tool):
    """
    Compute pairwise correlations for numeric columns and return a text-based heatmap (matrix).
    """

    name = "correlation_heatmap"
    description = "Compute pairwise correlation matrix for numeric columns; return as text table."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV"},
            "max_columns": {"type": "integer", "description": "Max columns (default 10)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_columns = kwargs.get("max_columns", 10)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(max_columns, int) or max_columns < 1:
            max_columns = 10
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
            numeric_cols = []
            for col in list(rows[0].keys())[:max_columns]:
                try:
                    arr = np.array([float(row.get(col, np.nan)) for row in rows], dtype=float)
                    if np.isnan(arr).all():
                        continue
                    numeric_cols.append((col, arr))
                except (ValueError, TypeError):
                    continue
            if len(numeric_cols) < 2:
                return "Need at least 2 numeric columns."
            names = [n for n, _ in numeric_cols]
            mat = np.column_stack([a for _, a in numeric_cols])
            corr = np.corrcoef(mat.T)
            lines = ["Correlation matrix", "=" * 40, "Columns: " + ", ".join(names), ""]
            for i, name in enumerate(names):
                parts = [f"{corr[i, j]:.2f}" for j in range(len(names))]
                lines.append(f"  {name}: " + " ".join(parts))
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


register(CorrelationHeatmapTool())
