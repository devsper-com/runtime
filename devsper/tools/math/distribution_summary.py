"""Summary statistics for a list of numbers: min, max, mean, median, quartiles."""

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DistributionSummaryTool(Tool):
    """Compute distribution summary: min, max, mean, median, Q1, Q3."""

    name = "distribution_summary"
    description = "Summary of numeric distribution: min, max, mean, median, quartiles."
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
            nums = sorted(float(v) for v in values)
        except (TypeError, ValueError):
            return "Error: all elements must be numbers"
        if not nums:
            return "Error: empty list"
        n = len(nums)
        mean = sum(nums) / n
        mid = n // 2
        median = (nums[mid - 1] + nums[mid]) / 2 if n % 2 == 0 else nums[mid]
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        q1 = nums[q1_idx]
        q3 = nums[q3_idx]
        return f"min = {nums[0]}\nmax = {nums[-1]}\nmean = {mean}\nmedian = {median}\nQ1 = {q1}\nQ3 = {q3}\nn = {n}"


register(DistributionSummaryTool())
