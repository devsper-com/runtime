"""Map-reduce plan for swarm: split items into batches (map), then aggregate keys (reduce)."""

import json

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class SwarmMapReduceTool(Tool):
    """
    Plan a map-reduce for swarm: split a list of items into map batches; suggest reduce keys.
    """

    name = "swarm_map_reduce"
    description = "Plan map-reduce for swarm: split items into map batches; return batch plan."
    input_schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "List of items to process (e.g. file paths or IDs)",
            },
            "batch_size": {"type": "integer", "description": "Items per map batch (default 5)"},
            "reduce_key": {"type": "string", "description": "Suggested key for reduce phase (e.g. sum, concat)"},
        },
        "required": ["items"],
    }

    def run(self, **kwargs) -> str:
        items = kwargs.get("items")
        batch_size = kwargs.get("batch_size", 5)
        reduce_key = kwargs.get("reduce_key") or "concat"
        if not items or not isinstance(items, list):
            return "Error: items must be a non-empty list"
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 5
        batches = [items[i : i + batch_size] for i in range(0, len(items), batch_size)]
        result = {"total_items": len(items), "batch_size": batch_size, "map_batches": len(batches), "batches": batches, "reduce_key": reduce_key}
        return json.dumps(result, indent=2)


register(SwarmMapReduceTool())
