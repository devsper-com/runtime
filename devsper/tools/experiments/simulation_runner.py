"""Run a simple simulation: e.g. N steps of a deterministic recurrence and return final state."""

from devsper.tools.base import Tool
from devsper.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class SimulationRunnerTool(Tool):
    """
    Run a simple numeric simulation: x_{n+1} = f(x_n) for N steps (e.g. linear growth).
    """

    name = "simulation_runner"
    description = "Run a simple simulation: recurrence for N steps (e.g. linear growth)."
    input_schema = {
        "type": "object",
        "properties": {
            "initial_value": {"type": "number", "description": "Starting value (default 1)"},
            "steps": {"type": "integer", "description": "Number of steps (default 10)"},
            "growth_rate": {"type": "number", "description": "Multiplier per step (default 1.1)"},
        },
        "required": [],
    }

    def run(self, **kwargs) -> str:
        initial = kwargs.get("initial_value", 1.0)
        steps = kwargs.get("steps", 10)
        growth_rate = kwargs.get("growth_rate", 1.1)
        if not isinstance(steps, int) or steps < 1:
            steps = 10
        x = initial
        trajectory = [x]
        for _ in range(steps - 1):
            x = x * growth_rate
            trajectory.append(x)
        return f"Simulation: initial={initial}, steps={steps}, growth_rate={growth_rate}. Final value: {x}. Trajectory (first 5, last 2): {trajectory[:5]} ... {trajectory[-2:]}"


register(SimulationRunnerTool())
