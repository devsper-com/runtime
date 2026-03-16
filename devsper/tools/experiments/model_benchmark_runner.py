"""Run a simple benchmark: execute a function N times and report mean/std of runtimes (mock or real)."""

import json
import time

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ModelBenchmarkRunnerTool(Tool):
    """
    Run a lightweight benchmark: repeat a no-op or fixed delay N times, report mean/std (for pipeline demos).
    """

    name = "model_benchmark_runner"
    description = "Run a simple timing benchmark (N iterations, optional delay) and report mean/std."
    input_schema = {
        "type": "object",
        "properties": {
            "iterations": {"type": "integer", "description": "Number of iterations (default 5)"},
            "delay_seconds": {"type": "number", "description": "Optional delay per iteration (default 0)"},
        },
        "required": [],
    }

    def run(self, **kwargs) -> str:
        iterations = kwargs.get("iterations", 5)
        delay_seconds = kwargs.get("delay_seconds", 0)
        if not isinstance(iterations, int) or iterations < 1:
            iterations = 5
        if not isinstance(delay_seconds, (int, float)) or delay_seconds < 0:
            delay_seconds = 0
        times = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            times.append(time.perf_counter() - t0)
        mean_t = sum(times) / len(times)
        variance = sum((t - mean_t) ** 2 for t in times) / len(times)
        std_t = variance ** 0.5
        return json.dumps({"iterations": iterations, "mean_seconds": round(mean_t, 4), "std_seconds": round(std_t, 4), "times": [round(t, 4) for t in times]}, indent=2)


register(ModelBenchmarkRunnerTool())
