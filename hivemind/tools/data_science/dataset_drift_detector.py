"""Detect simple distribution drift between two samples: compare mean and std."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class DatasetDriftDetectorTool(Tool):
    """
    Detect basic drift between two numeric samples: difference in mean and std.
    """

    name = "dataset_drift_detector"
    description = "Detect distribution drift between two numeric samples (mean, std comparison)."
    input_schema = {
        "type": "object",
        "properties": {
            "baseline": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Baseline sample",
            },
            "current": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Current sample",
            },
            "threshold_std": {"type": "number", "description": "Flag if mean diff > this many baseline stds (default 2)"},
        },
        "required": ["baseline", "current"],
    }

    def run(self, **kwargs) -> str:
        baseline = kwargs.get("baseline")
        current = kwargs.get("current")
        threshold_std = kwargs.get("threshold_std", 2.0)
        if not baseline or not isinstance(baseline, list):
            return "Error: baseline must be a non-empty list of numbers"
        if not current or not isinstance(current, list):
            return "Error: current must be a non-empty list of numbers"
        if np is None:
            return "Error: numpy is required for this tool"
        try:
            b = np.array(baseline, dtype=float)
            c = np.array(current, dtype=float)
            b, c = b[~np.isnan(b)], c[~np.isnan(c)]
        except (ValueError, TypeError):
            return "Error: values must be numeric"
        if len(b) < 2 or len(c) < 2:
            return "Error: need at least 2 values per sample"
        mean_b, std_b = np.mean(b), np.std(b)
        mean_c, std_c = np.mean(c), np.std(c)
        mean_diff = abs(mean_c - mean_b)
        std_b_safe = std_b if std_b > 0 else 1e-10
        z = mean_diff / std_b_safe
        drift = "Drift detected" if z > threshold_std else "No significant drift"
        return f"{drift}. Baseline: mean={mean_b:.4f}, std={std_b:.4f}. Current: mean={mean_c:.4f}, std={std_c:.4f}. Mean diff (in baseline stds): {z:.2f}"


register(DatasetDriftDetectorTool())
