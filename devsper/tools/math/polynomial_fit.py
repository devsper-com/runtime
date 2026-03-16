"""Fit a polynomial of given degree to x, y data. Uses numpy."""

from devsper.tools.base import Tool
from devsper.tools.registry import register


class PolynomialFitTool(Tool):
    """Fit polynomial coefficients to x and y. Returns coefficients (highest degree first)."""

    name = "polynomial_fit"
    description = "Fit polynomial of given degree to x, y. Returns coefficients."
    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "array", "description": "x values"},
            "y": {"type": "array", "description": "y values"},
            "degree": {"type": "integer", "description": "Polynomial degree (default 2)"},
        },
        "required": ["x", "y"],
    }

    def run(self, **kwargs) -> str:
        x = kwargs.get("x")
        y = kwargs.get("y")
        degree = kwargs.get("degree", 2)
        if not isinstance(x, list) or not isinstance(y, list):
            return "Error: x and y must be arrays"
        if len(x) != len(y) or len(x) < 2:
            return "Error: x and y must have same length >= 2"
        if not isinstance(degree, int) or degree < 1:
            degree = 2
        try:
            import numpy as np
            coefs = np.polyfit(x, y, degree)
            return "coefficients (high to low): " + str(coefs.tolist())
        except (ImportError, Exception) as e:
            return f"Error: {e}"


register(PolynomialFitTool())
