"""Generate a dataset profile: shape, dtypes, nulls, and basic stats. Uses CSV or numpy array description."""

import csv
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class DatasetProfileTool(Tool):
    """
    Profile a dataset from CSV or from a list of column arrays: shape, nulls, basic stats.
    """

    name = "dataset_profile"
    description = "Profile a dataset (CSV path or column lists): shape, nulls, basic stats."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV file"},
            "sample_rows": {"type": "integer", "description": "Max rows to sample for CSV (default 10000)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        sample_rows = kwargs.get("sample_rows", 10000)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(sample_rows, int) or sample_rows < 1:
            sample_rows = 10000
        p = Path(path).resolve()
        if not p.exists() or not p.is_file():
            return f"Error: file not found: {path}"
        try:
            with p.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if not rows:
                return "Empty CSV."
            header = rows[0]
            data = rows[1:][:sample_rows]
            n_rows, n_cols = len(data), len(header)
            null_counts = []
            for j in range(n_cols):
                col = [row[j] if j < len(row) else "" for row in data]
                nulls = sum(1 for c in col if c.strip() == "" or c.lower() in ("na", "nan", "none", "null"))
                null_counts.append(nulls)
            lines = [
                "Dataset profile",
                "=" * 40,
                f"Shape: {n_rows} rows, {n_cols} columns",
                f"Columns: {', '.join(header[:15])}" + ("..." if n_cols > 15 else ""),
                "Null-like counts per column:",
            ]
            for i, (h, nc) in enumerate(zip(header[:20], null_counts[:20])):
                lines.append(f"  {h}: {nc}")
            if np is not None and data:
                try:
                    arr = np.array(data, dtype=float, order="C")
                    mask = np.isnan(arr)
                    lines.append(f"\nNumeric stats (if applicable): min={np.nanmin(arr):.4f}, max={np.nanmax(arr):.4f}")
                except (ValueError, TypeError):
                    pass
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


register(DatasetProfileTool())
