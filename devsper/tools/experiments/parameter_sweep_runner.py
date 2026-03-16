"""Run a parameter sweep: generate (param_name, value) combinations and return as batch plan."""

import json

from devsper.tools.base import Tool
from devsper.tools.registry import register


class ParameterSweepRunnerTool(Tool):
    """
    Generate parameter sweep combinations from named parameter lists (no actual execution).
    """

    name = "parameter_sweep_runner"
    description = "Generate parameter sweep combinations from named parameter lists."
    input_schema = {
        "type": "object",
        "properties": {
            "params": {
                "type": "object",
                "description": "Map of param name -> list of values, e.g. {\"lr\": [0.01, 0.1], \"epochs\": [5, 10]}",
            },
            "max_combinations": {"type": "integer", "description": "Cap total combinations (default 100)"},
        },
        "required": ["params"],
    }

    def run(self, **kwargs) -> str:
        params = kwargs.get("params")
        max_combinations = kwargs.get("max_combinations", 100)
        if not params or not isinstance(params, dict):
            return "Error: params must be a dict of param name -> list of values"
        if not isinstance(max_combinations, int) or max_combinations < 1:
            max_combinations = 100
        names = list(params.keys())
        values = []
        for n in names:
            v = params[n]
            if not isinstance(v, list):
                v = [v]
            values.append(v)
        result = [{}]
        for i, vlist in enumerate(values):
            result = [r | {names[i]: x} for r in result for x in vlist]
            if len(result) > max_combinations:
                result = result[:max_combinations]
                break
        return json.dumps({"combinations": result, "total": len(result)}, indent=2)


register(ParameterSweepRunnerTool())
