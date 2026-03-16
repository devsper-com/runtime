"""Simple Monte Carlo: sample random values and report mean/std."""

import random

from devsper.tools.base import Tool
from devsper.tools.registry import register


class MonteCarloSimulationTool(Tool):
    """Run a simple Monte Carlo: N samples from uniform(a,b), return mean and std."""

    name = "monte_carlo_simulation"
    description = "Monte Carlo: N uniform samples in [a,b]. Returns mean and std."
    input_schema = {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "description": "Number of samples"},
            "a": {"type": "number", "description": "Lower bound"},
            "b": {"type": "number", "description": "Upper bound"},
        },
        "required": ["n", "a", "b"],
    }

    def run(self, **kwargs) -> str:
        n = kwargs.get("n")
        a = kwargs.get("a")
        b = kwargs.get("b")
        if not isinstance(n, int) or n < 1:
            return "Error: n must be a positive integer"
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return "Error: a and b must be numbers"
        if a >= b:
            return "Error: a must be less than b"
        values = [random.uniform(a, b) for _ in range(n)]
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        std = variance ** 0.5
        return f"n = {n}\nmean = {mean}\nstd = {std}"


register(MonteCarloSimulationTool())
