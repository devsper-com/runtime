"""Validate model input: check shapes, nulls, and value ranges for a list of arrays."""

from devsper.tools.base import Tool
from devsper.tools.registry import register

try:
    import numpy as np
except ImportError:
    np = None


class ModelInputValidatorTool(Tool):
    """
    Validate model inputs: check for NaNs, shapes, and optional value range.
    Accepts a single list of numbers (one array) or a JSON-like structure; validates and reports.
    """

    name = "model_input_validator"
    description = "Validate model input array: NaNs, shape, value range."
    input_schema = {
        "type": "object",
        "properties": {
            "values": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Single feature array",
            },
            "min_value": {"type": "number", "description": "Expected min (optional)"},
            "max_value": {"type": "number", "description": "Expected max (optional)"},
        },
        "required": ["values"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        min_value = kwargs.get("min_value")
        max_value = kwargs.get("max_value")
        if not values or not isinstance(values, list):
            return "Error: values must be a non-empty list of numbers"
        if np is None:
            return "Error: numpy is required for this tool"
        try:
            arr = np.array(values, dtype=float)
        except (ValueError, TypeError):
            return "Error: all values must be numeric"
        issues = []
        nan_count = int(np.isnan(arr).sum())
        if nan_count > 0:
            issues.append(f"NaNs: {nan_count}")
        if min_value is not None and np.nanmin(arr) < min_value:
            issues.append(f"Values below min {min_value}")
        if max_value is not None and np.nanmax(arr) > max_value:
            issues.append(f"Values above max {max_value}")
        if not issues:
            return f"Valid. Shape: {arr.shape}, no NaNs, range [{np.nanmin(arr):.4f}, {np.nanmax(arr):.4f}]"
        return "Validation issues: " + "; ".join(issues)


register(ModelInputValidatorTool())
