"""
Benchmark: dataset analysis (data science strategy, 4 tasks).
Uses mocked LLM.
"""

import time
from unittest.mock import patch

from hivemind.swarm.swarm import Swarm

MOCK_RESPONSE = "Dataset profile: ..."


def run_benchmark(iterations: int = 2) -> float:
    """Run dataset analysis-style task with mocked agent."""
    with (
        patch("hivemind.agents.agent.generate", return_value=MOCK_RESPONSE),
    ):
        swarm = Swarm(worker_count=2, worker_model="mock", planner_model="mock", use_tools=False)
        start = time.perf_counter()
        for _ in range(iterations):
            swarm.run("Load the dataset, profile it, and run basic analysis.")
        return time.perf_counter() - start


if __name__ == "__main__":
    elapsed = run_benchmark(iterations=2)
    print(f"bench_dataset_analysis: {elapsed:.2f}s for 2 runs")
