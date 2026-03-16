"""Grid search: same as parameter sweep, return grid of (param, value) combinations."""

import json

from devsper.tools.base import Tool
from devsper.tools.registry import register


class GridSearchRunnerTool(Tool):
    """
    Generate grid search combinations (full Cartesian product of parameter values).
    """

    name = "grid_search_runner"
    description = "Generate grid search parameter combinations (Cartesian product)."
    input_schema = {
        "type": "object",
        "properties": {
            "param_grid": {
                "type": "object",
                "description": "Map of param name -> list of values",
            },
            "max_combinations": {"type": "integer", "description": "Cap (default 50)"},
        },
        "required": ["param_grid"],
    }

    def run(self, **kwargs) -> str:
        param_grid = kwargs.get("param_grid")
        max_combinations = kwargs.get("max_combinations", 50)
        if not param_grid or not isinstance(param_grid, dict):
            return "Error: param_grid must be a dict of param name -> list of values"
        if not isinstance(max_combinations, int) or max_combinations < 1:
            max_combinations = 50
        names = list(param_grid.keys())
        values = []
        for n in names:
            v = param_grid[n]
            if not isinstance(v, list):
                v = [v]
            values.append(v)
        result = [{}]
        for i, vlist in enumerate(values):
            result = [r | {names[i]: x} for r in result for x in vlist]
        if len(result) > max_combinations:
            result = result[:max_combinations]
        return json.dumps({"grid_size": len(result), "combinations": result}, indent=2)


register(GridSearchRunnerTool())
