"""Detect outliers using IQR or z-score (simple heuristic)."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class DatasetOutlierDetectorTool(Tool):
    """
    Detect outliers in a numeric array using IQR (Q1 - 1.5*IQR, Q3 + 1.5*IQR) or z-score.
    """

    name = "dataset_outlier_detector"
    description = "Detect outliers in numeric data using IQR or z-score method."
    input_schema = {
        "type": "object",
        "properties": {
            "values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Numeric array",
            },
            "method": {"type": "string", "description": "iqr or zscore (default iqr)"},
            "z_threshold": {"type": "number", "description": "Z-score threshold (default 3.0)"},
        },
        "required": ["values"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        method = kwargs.get("method", "iqr")
        z_threshold = kwargs.get("z_threshold", 3.0)
        if not values or not isinstance(values, list):
            return "Error: values must be a non-empty list of numbers"
        if np is None:
            return "Error: numpy is required for this tool"
        try:
            arr = np.array(values, dtype=float)
            arr = arr[~np.isnan(arr)]
        except (ValueError, TypeError):
            return "Error: all values must be numeric"
        if len(arr) < 4:
            return "Error: need at least 4 values"
        if method == "zscore":
            mean, std = np.mean(arr), np.std(arr)
            if std == 0:
                return "No variance; no outliers."
            z = np.abs((arr - mean) / std)
            outliers = arr[z > z_threshold]
        else:
            q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
            iqr = q3 - q1
            if iqr == 0:
                return "IQR is 0; no outliers."
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outliers = arr[(arr < low) | (arr > high)]
        count = len(outliers)
        return f"Outliers: {count} ({100*count/len(arr):.1f}%). Sample (first 10): {outliers[:10].tolist()}"


register(DatasetOutlierDetectorTool())
