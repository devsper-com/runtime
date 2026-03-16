"""Track experiments: append or list experiment runs (in-memory or structured output for logging)."""

import json

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ExperimentTrackerTool(Tool):
    """
    Track experiment runs: record run_id, params, metric and return a log entry. Stateless; returns structured log.
    """

    name = "experiment_tracker"
    description = "Record an experiment run (run_id, params, metrics) and return log entry."
    input_schema = {
        "type": "object",
        "properties": {
            "run_id": {"type": "string", "description": "Run identifier"},
            "params": {"type": "object", "description": "Parameters used"},
            "metrics": {"type": "object", "description": "Metrics (e.g. accuracy, loss)"},
        },
        "required": ["run_id"],
    }

    def run(self, **kwargs) -> str:
        run_id = kwargs.get("run_id")
        params = kwargs.get("params") or {}
        metrics = kwargs.get("metrics") or {}
        if not run_id or not isinstance(run_id, str):
            return "Error: run_id must be a non-empty string"
        entry = {"run_id": run_id, "params": params, "metrics": metrics}
        return json.dumps({"logged": entry}, indent=2)


register(ExperimentTrackerTool())
