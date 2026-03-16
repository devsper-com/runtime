"""Generate a text report from experiment results (runs and metrics)."""

import json

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ExperimentReportGeneratorTool(Tool):
    """
    Generate a human-readable experiment report from a list of runs with params and metrics.
    """

    name = "experiment_report_generator"
    description = "Generate a text report from experiment results (runs, params, metrics)."
    input_schema = {
        "type": "object",
        "properties": {
            "runs": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of {run_id, params, metrics}",
            },
            "title": {"type": "string", "description": "Report title"},
        },
        "required": ["runs"],
    }

    def run(self, **kwargs) -> str:
        runs = kwargs.get("runs")
        title = kwargs.get("title") or "Experiment Report"
        if not runs or not isinstance(runs, list):
            return "Error: runs must be a non-empty list of {run_id, params, metrics}"
        lines = [title, "=" * 40, f"Total runs: {len(runs)}", ""]
        for i, r in enumerate(runs):
            if not isinstance(r, dict):
                continue
            run_id = r.get("run_id", f"run_{i}")
            params = r.get("params", {})
            metrics = r.get("metrics", r)
            lines.append(f"Run: {run_id}")
            if params:
                lines.append("  Params: " + json.dumps(params))
            if metrics and isinstance(metrics, dict):
                lines.append("  Metrics: " + json.dumps(metrics))
            lines.append("")
        return "\n".join(lines)


register(ExperimentReportGeneratorTool())
