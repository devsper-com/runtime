"""Split codebase analysis into batches for parallel/swarm processing."""

import json
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class ParallelCodebaseAnalysisTool(Tool):
    """
    Split a codebase into file batches for parallel analysis (e.g. by swarm workers).
    """

    name = "parallel_codebase_analysis"
    description = "Split codebase into batches for parallel analysis. Returns batch plan."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root path"},
            "batch_size": {"type": "integer", "description": "Files per batch (default 10)"},
            "extension": {"type": "string", "description": "File extension (default .py)"},
        },
        "required": ["path"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        batch_size = kwargs.get("batch_size", 10)
        extension = kwargs.get("extension", ".py")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 10
        root = Path(path).resolve()
        if not root.exists() or not root.is_dir():
            return f"Error: path must be an existing directory: {path}"
        files = [str(p.relative_to(root)).replace("\\", "/") for p in root.rglob(f"*{extension}") if p.is_file()]
        batches = [files[i : i + batch_size] for i in range(0, len(files), batch_size)]
        result = {"root": str(root), "total_files": len(files), "batch_size": batch_size, "num_batches": len(batches), "batches": batches}
        return json.dumps(result, indent=2)


register(ParallelCodebaseAnalysisTool())
