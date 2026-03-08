#!/usr/bin/env python3
"""
Experiment Runner: parameter grid → parameter_sweep_runner, swarm experiment runner, result_comparator → best config.

Workflow: parameter_sweep_runner → swarm experiment runner (or mock runs) → result_comparator
→ best configuration. Uses tools, memory, swarm runtime.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._common import get_memory_router, log, run_tool_safe, save_json, store_in_memory
from examples._config import get_planner_model, get_worker_model

from hivemind.swarm.swarm import Swarm
from hivemind.utils.event_logger import EventLog


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parameter sweep and select best configuration")
    parser.add_argument("--params", default=None, help='JSON params e.g. {"lr":[0.01,0.1],"epochs":[5,10]}')
    args = parser.parse_args()
    if args.params:
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError:
            params = {"lr": [0.01, 0.1], "epochs": [5, 10]}
    else:
        params = {"lr": [0.01, 0.1], "epochs": [5, 10], "batch_size": [16, 32]}

    log("Experiment Runner")
    log("Step 1: Parameter sweep runner (generate combinations)")
    sweep_out = run_tool_safe("parameter_sweep_runner", {"params": params, "max_combinations": 20})
    try:
        sweep_data = json.loads(sweep_out)
        combinations = sweep_data.get("combinations", [])
    except json.JSONDecodeError:
        combinations = [{"lr": 0.01, "epochs": 5}]

    log("Step 2: Mock experiment results (no real training)")
    results = []
    for i, config in enumerate(combinations[:8]):
        lr = config.get("lr", 0.01)
        epochs = config.get("epochs", 5)
        acc = 0.5 + 0.1 * (1 - lr) + 0.05 * min(epochs, 10) / 10 + (i % 3) * 0.02
        results.append({"run_id": f"run_{i}", "metrics": {"accuracy": round(acc, 4), "loss": round(1 - acc, 4)}, "config": config})

    log("Step 3: Result comparator (best by accuracy)")
    comparator_out = run_tool_safe(
        "result_comparator",
        {"results": results, "metric": "accuracy", "higher_is_better": True},
    )
    store_in_memory(comparator_out[:4000], "semantic", tags=["experiment", "best_config"])

    log("Step 4: Swarm summarize best configuration and recommendations")
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
        "Based on the experiment comparison in memory, summarize the best configuration and "
        "give one paragraph of recommendations for next experiments."
    )
    swarm_results = swarm.run(task)
    summary = next(iter(swarm_results.values()), "")

    out_data = {
        "sweep_combinations": len(combinations),
        "results_sample": results[:3],
        "comparator_output": comparator_out[:1500],
        "best_summary": summary,
    }
    path = save_json(out_data, "experiment_best_config.json")
    print(comparator_out)
    print("\n--- Swarm summary ---\n")
    print(summary)
    log(f"Saved: {path}")
    log("Done.")


if __name__ == "__main__":
    main()
