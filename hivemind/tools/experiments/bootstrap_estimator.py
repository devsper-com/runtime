"""Bootstrap estimate: resample with replacement B times and report mean and CI (percentile)."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
import random


class BootstrapEstimatorTool(Tool):
    """
    Bootstrap: resample with replacement B times, compute statistic (mean) each time; report mean and percentile CI.
    """

    name = "bootstrap_estimator"
    description = "Bootstrap resampling: report mean and percentile confidence interval."
    input_schema = {
        "type": "object",
        "properties": {
            "values": {"type": "array", "items": {"type": "number"}, "description": "Sample data"},
            "n_bootstrap": {"type": "integer", "description": "Number of bootstrap samples (default 200)"},
            "confidence": {"type": "number", "description": "CI level (default 0.95)"},
        },
        "required": ["values"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        n_bootstrap = kwargs.get("n_bootstrap", 200)
        confidence = kwargs.get("confidence", 0.95)
        if not values or not isinstance(values, list):
            return "Error: values must be a non-empty list of numbers"
        if not isinstance(n_bootstrap, int) or n_bootstrap < 1:
            n_bootstrap = 200
        if not isinstance(confidence, (int, float)) or confidence <= 0 or confidence >= 1:
            confidence = 0.95
        try:
            data = [float(x) for x in values]
        except (ValueError, TypeError):
            return "Error: all values must be numeric"
        if len(data) < 2:
            return "Error: need at least 2 values"
        n = len(data)
        means = []
        for _ in range(n_bootstrap):
            sample = random.choices(data, k=n)
            means.append(sum(sample) / n)
        means.sort()
        alpha = 1 - confidence
        lo = means[int(alpha / 2 * n_bootstrap)]
        hi = means[int((1 - alpha / 2) * n_bootstrap)]
        point = sum(data) / len(data)
        return f"Bootstrap (n={len(data)}, B={n_bootstrap}): point estimate={point:.4f}, {int(confidence*100)}% CI = [{lo:.4f}, {hi:.4f}]"


register(BootstrapEstimatorTool())
