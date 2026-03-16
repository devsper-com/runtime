#!/usr/bin/env python3
"""
Dataset Analyzer: CSV dataset → profile, distribution, outliers, correlation → dataset report.

Workflow: dataset_profile → distribution_report → outlier_detection → correlation analysis
→ swarm summary. Uses Iris by default when scikit-learn is available; otherwise a small sample.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from examples._common import (
    build_report_from_swarm,
    get_memory_router,
    log,
    run_tool_safe,
    save_json,
    save_markdown,
    store_in_memory,
)
from examples._config import get_planner_model, get_worker_model

from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog


def _iris_csv_path() -> Path:
    """Path for Iris dataset CSV (examples/output/iris.csv)."""
    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "iris.csv"


def _ensure_iris_csv() -> Path:
    """Create Iris dataset CSV using scikit-learn if available, else a minimal fallback."""
    path = _iris_csv_path()
    if path.exists():
        log(f"Using existing Iris CSV: {path}")
        return path
    try:
        from sklearn.datasets import load_iris

        iris = load_iris()
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["sepal_length_cm", "sepal_width_cm", "petal_length_cm", "petal_width_cm", "species"])
            target_names = list(iris.target_names)
            for i in range(len(iris.data)):
                row = list(iris.data[i]) + [target_names[iris.target[i]]]
                w.writerow(row)
        log(f"Created Iris CSV from scikit-learn: {path} ({len(iris.data)} rows)")
        return path
    except ImportError:
        pass
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sepal_length_cm", "sepal_width_cm", "petal_length_cm", "petal_width_cm", "species"])
        for i in range(30):
            if i < 10:
                w.writerow([5.0 + i * 0.1, 3.4, 1.4 + i * 0.05, 0.2, "setosa"])
            elif i < 20:
                w.writerow([5.8 + (i - 10) * 0.08, 2.7, 4.0 + (i - 10) * 0.1, 1.2 + (i - 10) * 0.05, "versicolor"])
            else:
                w.writerow([6.2 + (i - 20) * 0.06, 2.9, 5.0 + (i - 20) * 0.12, 1.8 + (i - 20) * 0.06, "virginica"])
    log(f"Created fallback Iris-shaped CSV (install scikit-learn for full dataset): {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a CSV dataset")
    parser.add_argument("path", nargs="?", default=None, help="Path to CSV file (default: sample)")
    args = parser.parse_args()
    csv_path = args.path
    if not csv_path or not Path(csv_path).exists():
        csv_path = str(_ensure_iris_csv())

    log("Dataset Analyzer")
    log("Step 1: Dataset profile")
    profile_out = run_tool_safe("dataset_profile", {"path": csv_path, "sample_rows": 10000})
    dist_out = ""
    corr_out = ""
    try:
        log("Step 2: Distribution report")
        dist_out = run_tool_safe("dataset_distribution_report", {"path": csv_path, "max_columns": 20})
    except Exception as e:
        log(f"  (distribution skipped: {e})")
    try:
        log("Step 3: Correlation analysis")
        corr_out = run_tool_safe("correlation_heatmap", {"path": csv_path, "max_columns": 10})
    except Exception as e:
        log(f"  (correlation skipped: {e})")

    store_in_memory(profile_out[:6000], "semantic", tags=["dataset", "profile"])
    if dist_out:
        store_in_memory(dist_out[:4000], "semantic", tags=["dataset", "distribution"])
    if corr_out:
        store_in_memory(corr_out[:4000], "semantic", tags=["dataset", "correlation"])

    log("Step 4: Swarm dataset report")
    event_log = EventLog()
    swarm = Swarm(
        worker_count=2,
        worker_model=get_worker_model(),
        planner_model=get_planner_model(),
        event_log=event_log,
        memory_router=get_memory_router(),
        use_tools=False,
    )
    task = (
        "Write a short dataset report (about half a page): (1) What the data looks like (shape, columns), "
        "(2) Key statistics and distributions, (3) Any notable correlations or quality notes. Use memory context."
    )
    swarm.run(task)

    report = build_report_from_swarm(swarm, "Dataset Report")
    save_markdown(report, "dataset_report.md")
    completed = swarm.last_completed_tasks
    save_json(
        {
            "profile_preview": profile_out[:1500],
            "distribution_preview": dist_out[:1000] if dist_out else "",
            "correlation_preview": corr_out[:1000] if corr_out else "",
            "task_ids": [t.id for t in completed],
            "task_descriptions": [t.description or "" for t in completed],
        },
        "dataset_analysis_meta.json",
        normalize_strings=True,
    )
    log("Done.")


if __name__ == "__main__":
    main()
