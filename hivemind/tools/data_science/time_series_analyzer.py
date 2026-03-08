"""Basic time series analysis: trend (linear slope), simple stats. Assumes numeric column as series."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class TimeSeriesAnalyzerTool(Tool):
    """
    Analyze a time series (numeric list): linear trend slope, mean, std, min, max.
    """

    name = "time_series_analyzer"
    description = "Analyze time series: trend slope, mean, std, min, max."
    input_schema = {
        "type": "object",
        "properties": {
            "values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Time series values (ordered)",
            },
        },
        "required": ["values"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        if not values or not isinstance(values, list):
            return "Error: values must be a non-empty list of numbers"
        if np is None:
            return "Error: numpy is required for this tool"
        try:
            arr = np.array(values, dtype=float)
            arr = arr[~np.isnan(arr)]
        except (ValueError, TypeError):
            return "Error: all values must be numeric"
        if len(arr) < 2:
            return "Error: need at least 2 values"
        x = np.arange(len(arr), dtype=float)
        slope = np.polyfit(x, arr, 1)[0]
        lines = [
            "Time series summary",
            "=" * 40,
            f"Length: {len(arr)}",
            f"Mean: {np.mean(arr):.4f}, Std: {np.std(arr):.4f}",
            f"Min: {np.min(arr):.4f}, Max: {np.max(arr):.4f}",
            f"Linear trend slope: {slope:.6f}",
        ]
        return "\n".join(lines)


register(TimeSeriesAnalyzerTool())
