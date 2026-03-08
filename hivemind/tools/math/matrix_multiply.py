"""Multiply two matrices (lists of lists). Uses numpy if available."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class MatrixMultiplyTool(Tool):
    """Multiply two matrices given as JSON arrays. Uses numpy."""

    name = "matrix_multiply"
    description = "Multiply two matrices (list of lists). Requires numpy."
    input_schema = {
        "type": "object",
        "properties": {
            "matrix_a": {"type": "array", "description": "First matrix (list of rows)"},
            "matrix_b": {"type": "array", "description": "Second matrix (list of rows)"},
        },
        "required": ["matrix_a", "matrix_b"],
    }

    def run(self, **kwargs) -> str:
        a = kwargs.get("matrix_a")
        b = kwargs.get("matrix_b")
        if not isinstance(a, list) or not isinstance(b, list):
            return "Error: matrix_a and matrix_b must be arrays"
        try:
            import numpy as np
            A = np.array(a)
            B = np.array(b)
            C = A @ B
            return str(C.tolist())
        except ImportError:
            return "Error: numpy required"
        except Exception as e:
            return f"Error: {e}"


register(MatrixMultiplyTool())
