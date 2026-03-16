"""Split a dataset (row indices or file) into batches for distributed/swarm processing."""

import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register


class DistributedDatasetProcessorTool(Tool):
    """
    Split dataset processing into batches: given total rows or a CSV path, return batch ranges.
    """

    name = "distributed_dataset_processor"
    description = "Split dataset into batches for distributed processing. Returns batch plan."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV (to count rows) or use total_rows"},
            "total_rows": {"type": "integer", "description": "Total rows if known"},
            "batch_size": {"type": "integer", "description": "Rows per batch (default 1000)"},
        },
        "required": [],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        total_rows = kwargs.get("total_rows")
        batch_size = kwargs.get("batch_size", 1000)
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 1000
        if total_rows is not None and isinstance(total_rows, int) and total_rows > 0:
            n = total_rows
        elif path and isinstance(path, str):
            p = Path(path).resolve()
            if not p.exists() or not p.is_file():
                return f"Error: file not found: {path}"
            try:
                n = sum(1 for _ in p.open(encoding="utf-8", errors="replace")) - 1
                n = max(0, n)
            except Exception as e:
                return f"Error: {e}"
        else:
            return "Error: provide path (to CSV) or total_rows"
        batches = []
        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            batches.append({"start": start, "end": end, "size": end - start})
        result = {"total_rows": n, "batch_size": batch_size, "num_batches": len(batches), "batches": batches}
        return json.dumps(result, indent=2)


register(DistributedDatasetProcessorTool())
