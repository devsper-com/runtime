"""
Benchmark: research pipeline (strategy DAG or small literature-style workflow).
Uses mocked LLM so it is fast and deterministic.
"""

import time
from unittest.mock import patch

from hivemind.swarm.swarm import Swarm

MOCK_RESPONSE = "Summary of diffusion models: ..."


def run_benchmark(iterations: int = 2) -> float:
    """Run research-style task (triggers research strategy, 4 tasks) with mocked agent."""
    with (
        patch("hivemind.agents.agent.generate", return_value=MOCK_RESPONSE),
    ):
        swarm = Swarm(worker_count=2, worker_model="mock", planner_model="mock", use_tools=False)
        start = time.perf_counter()
        for _ in range(iterations):
            swarm.run("Analyze diffusion model research and summarize key papers.")
        return time.perf_counter() - start


if __name__ == "__main__":
    elapsed = run_benchmark(iterations=2)
    print(f"bench_research_pipeline: {elapsed:.2f}s for 2 runs")
