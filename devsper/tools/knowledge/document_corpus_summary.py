"""Summarize a document corpus: total size, doc counts, and aggregate stats."""

import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown, DOCPROC_EXTENSIONS


class DocumentCorpusSummaryTool(Tool):
    """
    Produce an aggregate summary of a corpus: number of docs, total chars, by-extension counts.
    """

    name = "document_corpus_summary"
    description = "Summarize a document corpus: doc count, total size, and stats per format."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of paths to documents",
            },
            "directory": {"type": "string", "description": "Alternatively, directory to scan for docs"},
        },
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        directory = kwargs.get("directory")
        paths = []
        if file_paths and isinstance(file_paths, list):
            paths = [p for p in file_paths if isinstance(p, str) and p.strip()]
        if directory and isinstance(directory, str):
            d = Path(directory).resolve()
            if d.exists() and d.is_dir():
                for ext in DOCPROC_EXTENSIONS:
                    paths.extend(str(p) for p in d.rglob(f"*{ext}"))
        if not paths:
            return "Error: provide file_paths (list) or directory (path to folder)"
        by_ext = {}
        total_chars = 0
        success = 0
        for path in paths:
            p = Path(path).resolve()
            if not p.exists() or not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext not in DOCPROC_EXTENSIONS:
                continue
            by_ext[ext] = by_ext.get(ext, 0) + 1
            content, err = run_docproc_to_markdown(str(p))
            if err:
                continue
            success += 1
            total_chars += len(content or "")
        summary = {
            "total_documents": len(paths),
            "successfully_processed": success,
            "total_characters": total_chars,
            "by_extension": by_ext,
        }
        return json.dumps(summary, indent=2)


register(DocumentCorpusSummaryTool())
