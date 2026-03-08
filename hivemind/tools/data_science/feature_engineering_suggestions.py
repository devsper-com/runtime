"""Suggest simple feature engineering: log, sqrt, squared, binning for numeric columns."""

import csv
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class FeatureEngineeringSuggestionsTool(Tool):
    """
    Suggest feature engineering based on column stats: log (if positive), sqrt, squared, binning.
    """

    name = "feature_engineering_suggestions"
    description = "Suggest feature engineering: log, sqrt, squared, binning for numeric columns."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV"},
            "max_columns": {"type": "integer", "description": "Max columns (default 15)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        max_columns = kwargs.get("max_columns", 15)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
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
            lines = ["Feature engineering suggestions", "=" * 40]
            for col in list(rows[0].keys())[:max_columns]:
                try:
                    arr = np.array([float(row.get(col, np.nan)) for row in rows], dtype=float)
                    arr = arr[~np.isnan(arr)]
                    if len(arr) < 3:
                        continue
                    min_v, max_v = np.min(arr), np.max(arr)
                    sugs = []
                    if min_v > 0:
                        sugs.append("log1p")
                    sugs.append("sqrt(abs(x))")
                    sugs.append("squared")
                    sugs.append("binned (e.g. quintiles)")
                    lines.append(f"  {col}: " + ", ".join(sugs))
                except (ValueError, TypeError):
                    continue
            return "\n".join(lines) if len(lines) > 1 else "No numeric columns found."
        except Exception as e:
            return f"Error: {e}"


register(FeatureEngineeringSuggestionsTool())
