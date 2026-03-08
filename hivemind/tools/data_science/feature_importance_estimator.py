"""Estimate feature importance using simple correlation with a target column (no model)."""

import csv
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class FeatureImportanceEstimatorTool(Tool):
    """
    Estimate feature importance as absolute correlation with target (numeric). No model training.
    """

    name = "feature_importance_estimator"
    description = "Estimate feature importance via correlation with target column (numeric)."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV"},
            "target_column": {"type": "string", "description": "Name of target column"},
            "top_n": {"type": "integer", "description": "Top N features (default 15)"},
        },
        "required": ["path", "target_column"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        target_column = kwargs.get("target_column")
        top_n = kwargs.get("top_n", 15)
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not target_column or not isinstance(target_column, str):
            return "Error: target_column must be a non-empty string"
        if not isinstance(top_n, int) or top_n < 1:
            top_n = 15
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
            headers = list(rows[0].keys())
            if target_column not in headers:
                return f"Error: target column '{target_column}' not in {headers}"
            try:
                y = np.array([float(row.get(target_column, np.nan)) for row in rows], dtype=float)
            except (ValueError, TypeError):
                return "Error: target column must be numeric"
            importance = []
            for col in headers:
                if col == target_column:
                    continue
                try:
                    x = np.array([float(row.get(col, np.nan)) for row in rows], dtype=float)
                    mask = ~(np.isnan(x) | np.isnan(y))
                    if mask.sum() < 3:
                        continue
                    c = np.corrcoef(x[mask], y[mask])[0, 1]
                    importance.append((col, abs(float(c))))
                except (ValueError, TypeError):
                    continue
            importance.sort(key=lambda t: -t[1])
            lines = ["Feature importance (|correlation| with target)", "=" * 40]
            for name, val in importance[:top_n]:
                lines.append(f"  {name}: {val:.4f}")
            return "\n".join(lines) if lines else "No numeric features to correlate."
        except Exception as e:
            return f"Error: {e}"


register(FeatureImportanceEstimatorTool())
