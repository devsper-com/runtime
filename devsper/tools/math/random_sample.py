"""Draw a random sample from a list of values."""

import random

from devsper.tools.base import Tool
from devsper.tools.registry import register


class RandomSampleTool(Tool):
    """Return k random items from a list (without replacement)."""

    name = "random_sample"
    description = "Draw k random elements from a list without replacement."
    input_schema = {
        "type": "object",
        "properties": {
            "values": {"type": "array", "description": "List of values"},
            "k": {"type": "integer", "description": "Number of items to sample"},
        },
        "required": ["values", "k"],
    }

    def run(self, **kwargs) -> str:
        values = kwargs.get("values")
        k = kwargs.get("k")
        if not isinstance(values, list):
            return "Error: values must be an array"
        if not isinstance(k, int) or k < 1:
            return "Error: k must be a positive integer"
        if k > len(values):
            return "Error: k cannot exceed list length"
        sample = random.sample(values, k)
        return str(sample)


register(RandomSampleTool())
