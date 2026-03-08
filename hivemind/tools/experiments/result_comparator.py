"""Compare two or more experiment results (metrics) and report best by a chosen metric."""

import json

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ResultComparatorTool(Tool):
    """
    Compare experiment results: pass list of {run_id, metrics}; choose metric and direction (max/min).
    """

    name = "result_comparator"
    description = "Compare experiment results by a chosen metric; return best run and summary."
    input_schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of {run_id, metrics}",
            },
            "metric": {"type": "string", "description": "Metric name to compare (e.g. accuracy)"},
            "higher_is_better": {"type": "boolean", "description": "True for accuracy, False for loss (default True)"},
        },
        "required": ["results", "metric"],
    }

    def run(self, **kwargs) -> str:
        results = kwargs.get("results")
        metric = kwargs.get("metric")
        higher_is_better = kwargs.get("higher_is_better", True)
        if not results or not isinstance(results, list):
            return "Error: results must be a non-empty list of {run_id, metrics}"
        if not metric or not isinstance(metric, str):
            return "Error: metric must be a non-empty string"
        comparable = []
        for r in results:
            if not isinstance(r, dict):
                continue
            run_id = r.get("run_id", "?")
            metrics = r.get("metrics") or r
            if metric not in metrics:
                continue
            try:
                val = float(metrics[metric])
                comparable.append((run_id, val, r))
            except (TypeError, ValueError):
                continue
        if not comparable:
            return f"No results with metric '{metric}' found."
        comparable.sort(key=lambda x: x[1], reverse=higher_is_better)
        best = comparable[0]
        return json.dumps({"best_run_id": best[0], "best_value": best[1], "all_ranked": [{"run_id": x[0], "value": x[1]} for x in comparable]}, indent=2)


register(ResultComparatorTool())
