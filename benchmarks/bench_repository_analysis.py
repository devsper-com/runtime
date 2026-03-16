"""
Benchmark: repository analysis (code analysis strategy, 4 tasks).
Uses mocked LLM.
"""

import time
from unittest.mock import patch

from devsper.swarm.swarm import Swarm

MOCK_RESPONSE = "Repository structure: ..."


def run_benchmark(iterations: int = 2) -> float:
    """Run code analysis-style task with mocked agent."""
    with (
        patch("devsper.agents.agent.generate", return_value=MOCK_RESPONSE),
    ):
        swarm = Swarm(worker_count=2, worker_model="mock", planner_model="mock", use_tools=False)
        start = time.perf_counter()
        for _ in range(iterations):
            swarm.run("Analyze the codebase architecture and dependencies.")
        return time.perf_counter() - start


if __name__ == "__main__":
    elapsed = run_benchmark(iterations=2)
    print(f"bench_repository_analysis: {elapsed:.2f}s for 2 runs")
