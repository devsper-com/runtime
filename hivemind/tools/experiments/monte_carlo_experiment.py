"""Run a Monte Carlo experiment: sample N times from a simple distribution and report stats."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
import random


class MonteCarloExperimentTool(Tool):
    """
    Run a Monte Carlo experiment: N random samples (e.g. uniform or from a list) and report mean/std.
    """

    name = "monte_carlo_experiment"
    description = "Run Monte Carlo: N samples, report mean, std, min, max."
    input_schema = {
        "type": "object",
        "properties": {
            "n_samples": {"type": "integer", "description": "Number of samples (default 100)"},
            "low": {"type": "number", "description": "Uniform low (default 0)"},
            "high": {"type": "number", "description": "Uniform high (default 1)"},
        },
        "required": [],
    }

    def run(self, **kwargs) -> str:
        n_samples = kwargs.get("n_samples", 100)
        low = kwargs.get("low", 0.0)
        high = kwargs.get("high", 1.0)
        if not isinstance(n_samples, int) or n_samples < 1:
            n_samples = 100
        samples = [random.uniform(low, high) for _ in range(n_samples)]
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        std = variance ** 0.5
        return f"Monte Carlo (n={n_samples}, uniform [{low},{high}]): mean={mean:.4f}, std={std:.4f}, min={min(samples):.4f}, max={max(samples):.4f}"


register(MonteCarloExperimentTool())
