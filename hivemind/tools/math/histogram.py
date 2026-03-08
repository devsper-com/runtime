"""Compute histogram (count per bin) for a list of numbers."""

from collections import defaultdict

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class HistogramTool(Tool):
    """Compute histogram: bin edges and counts. Optional number of bins."""

    name = "histogram"
    description = "Compute histogram of values. Returns bin ranges and counts."
    input_schema = {
        "type": "object",
        "properties": {
            "values": {"type": "array", "description": "List of numbers"},
            "bins": {"type": "integer", "description": "Number of bins (default 10)"},
        },
        "required": ["values"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        bins = kwargs.get("bins", 10)
        if not isinstance(values, list):
            return "Error: values must be an array"
        if not isinstance(bins, int) or bins < 1:
            bins = 10
        try:
            nums = [float(v) for v in values]
        except (TypeError, ValueError):
            return "Error: all elements must be numbers"
        if not nums:
            return "Error: empty list"
        lo = min(nums)
        hi = max(nums)
        if hi == lo:
            return f"All values equal: {lo}\ncount: {len(nums)}"
        width = (hi - lo) / bins
        counts = [0] * bins
        for v in nums:
            idx = min(int((v - lo) / width), bins - 1) if width > 0 else 0
            counts[idx] += 1
        lines = []
        for i in range(bins):
            left = lo + i * width
            right = lo + (i + 1) * width
            lines.append(f"[{left:.2f}, {right:.2f}): {counts[i]}")
        return "\n".join(lines)


register(HistogramTool())
