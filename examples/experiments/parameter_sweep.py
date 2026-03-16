#!/usr/bin/env python3
"""
Parameter sweep: grid_search_runner → swarm_experiment_runner.

Workflow: generate parameter grid → run swarm experiment for each combination (or sample)
→ report best configuration. Standalone example.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import devsper.tools  # noqa: F401
from devsper.tools.tool_runner import run_tool
from examples._common import examples_output_dir, log


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parameter sweep with grid search and swarm experiments"
    )
    parser.add_argument(
        "--params",
        type=str,
        default='{"lr": [0.01, 0.1], "batch_size": [16, 32]}',
        help="JSON object: param name -> list of values",
    )
    parser.add_argument(
        "--max-combinations", type=int, default=10, help="Cap grid size"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="Runs per combination for swarm_experiment_runner",
    )
    args = parser.parse_args()

    try:
        param_grid = json.loads(args.params)
    except json.JSONDecodeError as e:
        log(f"Error: invalid --params JSON: {e}")
        sys.exit(1)

    log("Parameter Sweep")
    log("Step 1: Grid search runner")
    grid_out = run_tool(
        "grid_search_runner",
        {"param_grid": param_grid, "max_combinations": args.max_combinations},
    )
    log(f"  {grid_out[:500]}...")
    try:
        grid_data = json.loads(grid_out)
        combinations = grid_data.get("combinations", [])
    except json.JSONDecodeError:
        log("  Could not parse grid output")
        combinations = [param_grid]

    log("Step 2: Swarm experiment runner (per combination or sample)")
    results = []
    for i, combo in enumerate(combinations[:5]):
        task_desc = f"Simulate experiment with config: {json.dumps(combo)}"
        exp_out = run_tool(
            "swarm_experiment_runner",
            {"parameters": {"task": task_desc}, "runs": args.runs},
        )
        try:
            exp_data = json.loads(exp_out)
            results.append({"combination": combo, "stats": exp_data})
        except json.JSONDecodeError:
            results.append({"combination": combo, "raw": exp_out[:300]})

    out_dir = examples_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "parameter_sweep_meta.json"
    with open(meta_path, "w") as f:
        json.dump({"grid_size": len(combinations), "results": results}, f, indent=2)
    log(f"Saved: {meta_path}")
    log("Done.")


if __name__ == "__main__":
    main()
