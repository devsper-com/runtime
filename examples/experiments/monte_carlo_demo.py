#!/usr/bin/env python3
"""
Monte Carlo Simulation Demo: simulation parameters → monte_carlo_experiment → result aggregation → statistical summary.

Workflow: monte_carlo_experiment (possibly multiple runs) → result aggregation
→ swarm summary. Uses tools, swarm runtime.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._common import get_memory_router, log, run_tool_safe, save_json, store_in_memory
from examples._config import get_planner_model, get_worker_model

from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Monte Carlo simulation demo")
    parser.add_argument("--n", type=int, default=500, help="Number of samples per run")
    parser.add_argument("--runs", type=int, default=3, help="Number of Monte Carlo runs to aggregate")
    parser.add_argument("--low", type=float, default=0.0, help="Uniform low")
    parser.add_argument("--high", type=float, default=1.0, help="Uniform high")
    args = parser.parse_args()

    log("Monte Carlo Demo")
    results = []
    for i in range(args.runs):
        log(f"Run {i+1}/{args.runs}: monte_carlo_experiment n={args.n}")
        out = run_tool_safe("monte_carlo_experiment", {"n_samples": args.n, "low": args.low, "high": args.high})
        results.append(out)
    aggregated = "\n---\n".join(results)
    store_in_memory(aggregated[:6000], "semantic", tags=["monte_carlo", "aggregated"])

    log("Swarm: statistical summary of Monte Carlo results")
    event_log = EventLog()
    swarm = Swarm(
        worker_count=1,
        worker_model=get_worker_model(),
        planner_model=get_planner_model(),
        event_log=event_log,
        memory_router=get_memory_router(),
        use_tools=False,
    )
    task = (
        "Summarize the Monte Carlo experiment results from memory in 2–3 sentences: "
        "what was simulated, the reported mean/std, and a brief interpretation."
    )
    swarm_results = swarm.run(task)
    summary = next(iter(swarm_results.values()), "")

    out_data = {
        "n_samples": args.n,
        "runs": args.runs,
        "low": args.low,
        "high": args.high,
        "raw_results": results,
        "statistical_summary": summary,
    }
    path = save_json(out_data, "monte_carlo_summary.json")
    print(aggregated)
    print("\n--- Swarm summary ---\n")
    print(summary)
    log(f"Saved: {path}")
    log("Done.")


if __name__ == "__main__":
    main()
