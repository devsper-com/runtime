"""Compute Pearson correlation between two lists of numbers."""

from devsper.tools.base import Tool
from devsper.tools.registry import register


class CorrelationTool(Tool):
    """Compute Pearson correlation coefficient between x and y."""

    name = "correlation"
    description = "Compute Pearson correlation between two lists of numbers."
    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "array", "description": "First list of numbers"},
            "y": {"type": "array", "description": "Second list of numbers"},
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
            X = [float(v) for v in x]
            Y = [float(v) for v in y]
        except (TypeError, ValueError):
            return "Error: all elements must be numbers"
        n = len(X)
        mx = sum(X) / n
        my = sum(Y) / n
        sx = (sum((a - mx) ** 2 for a in X) / n) ** 0.5
        sy = (sum((b - my) ** 2 for b in Y) / n) ** 0.5
        if sx == 0 or sy == 0:
            return "Error: zero variance in x or y"
        r = sum((X[i] - mx) * (Y[i] - my) for i in range(n)) / (n * sx * sy)
        return f"Pearson r = {r}"


register(CorrelationTool())
