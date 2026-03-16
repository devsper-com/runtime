"""Analyze multiple documents in batches (swarm-friendly: split into chunks for parallel workers)."""

import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown, DOCPROC_EXTENSIONS


class ParallelDocumentAnalyzerTool(Tool):
    """
    Split a list of documents into batches for parallel analysis (e.g. by a swarm).
    Returns batch assignments and per-batch file lists; does not run docproc itself.
    """

    name = "parallel_document_analyzer"
    description = "Split documents into batches for parallel/swarm analysis. Returns batch plan."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to documents",
            },
            "directory": {"type": "string", "description": "Or directory to scan for docs"},
            "batch_size": {"type": "integer", "description": "Documents per batch (default 5)"},
        },
        "required": [],
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        directory = kwargs.get("directory")
        batch_size = kwargs.get("batch_size", 5)
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 5
        paths = []
        if file_paths and isinstance(file_paths, list):
            paths = [p for p in file_paths if isinstance(p, str) and p.strip()]
        if directory and isinstance(directory, str):
            d = Path(directory).resolve()
            if d.exists() and d.is_dir():
                for ext in DOCPROC_EXTENSIONS:
                    paths.extend(str(p) for p in d.rglob(f"*{ext}"))
        if not paths:
            return "Error: provide file_paths or directory"
        batches = []
        for i in range(0, len(paths), batch_size):
            batches.append(paths[i : i + batch_size])
        result = {"total_documents": len(paths), "batch_size": batch_size, "num_batches": len(batches), "batches": batches}
        return json.dumps(result, indent=2)


register(ParallelDocumentAnalyzerTool())
