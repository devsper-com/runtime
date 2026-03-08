"""Simple linear regression: y = mx + b from lists of x and y."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class LinearRegressionTool(Tool):
    """Fit y = mx + b to x and y lists. Returns slope and intercept."""

    name = "linear_regression"
    description = "Fit linear regression to x and y data. Returns slope m and intercept b."
    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "array", "description": "List of x values (numbers)"},
            "y": {"type": "array", "description": "List of y values (numbers)"},
        },
        "required": ["x", "y"],
    }

    def run(self, **kwargs) -> str:
        x = kwargs.get("x")
        y = kwargs.get("y")
        if not isinstance(x, list) or not isinstance(y, list):
            return "Error: x and y must be arrays"
        if len(x) != len(y) or len(x) < 2:
            return "Error: x and y must have same length >= 2"
        try:
            import numpy as np
            X = np.array(x, dtype=float)
            Y = np.array(y, dtype=float)
            n = len(X)
            sx = X.sum()
            sy = Y.sum()
            sxy = (X * Y).sum()
            sxx = (X * X).sum()
            denom = n * sxx - sx * sx
            if abs(denom) < 1e-12:
                return "Error: singular (collinear) data"
            m = (n * sxy - sx * sy) / denom
            b = (sy - m * sx) / n
            return f"slope m = {m}\nintercept b = {b}\ny = {m}*x + {b}"
        except (ImportError, ValueError, TypeError) as e:
            return f"Error: {e}"


register(LinearRegressionTool())
