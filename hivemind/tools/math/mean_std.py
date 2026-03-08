"""Compute mean and standard deviation of a list of numbers."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class MeanStdTool(Tool):
    """Compute mean and standard deviation of a list of numbers."""

    name = "mean_std"
    description = "Compute mean and standard deviation of a list of numbers."
    input_schema = {
        "type": "object",
        "properties": {"values": {"type": "array", "description": "List of numbers"}},
        "required": ["values"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        if not isinstance(values, list):
            return "Error: values must be an array"
        try:
            nums = [float(v) for v in values]
        except (TypeError, ValueError):
            return "Error: all elements must be numbers"
        if not nums:
            return "Error: empty list"
        n = len(nums)
        mean = sum(nums) / n
        variance = sum((x - mean) ** 2 for x in nums) / n
        std = variance ** 0.5
        return f"mean = {mean}\nstd = {std}\nn = {n}"


register(MeanStdTool())
