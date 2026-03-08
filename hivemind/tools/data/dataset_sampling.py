"""Sample N random rows from a CSV."""

import csv
import random
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class DatasetSamplingTool(Tool):
    """Return a random sample of N rows from a CSV file."""

    name = "dataset_sampling"
    description = "Sample N random rows from a CSV. Returns sampled rows as text."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to CSV"},
            "n": {"type": "integer", "description": "Number of rows to sample"},
        },
        "required": ["path", "n"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        n = kwargs.get("n")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(n, int) or n < 1:
            return "Error: n must be a positive integer"
        p = Path(path)
        if not p.exists() or not p.is_file():
            return f"Error: file not found: {path}"
        try:
            with p.open(encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            if not rows:
                return "Empty CSV."
            header = rows[0]
            data = rows[1:]
            if n >= len(data):
                sample = data
            else:
                sample = random.sample(data, n)
            lines = [",".join(header)]
            for row in sample:
                lines.append(",".join(str(c) for c in row))
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"


register(DatasetSamplingTool())
