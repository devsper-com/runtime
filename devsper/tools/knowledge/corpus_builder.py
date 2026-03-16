"""Build a text corpus from a list of document paths (PDF, DOCX, etc.) using docproc."""

import json
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown, DOCPROC_EXTENSIONS


class CorpusBuilderTool(Tool):
    """
    Build a structured corpus from multiple documents.
    Extracts text via docproc and returns a JSON-like summary with paths and excerpt lengths.
    """

    name = "corpus_builder"
    description = "Build a text corpus from multiple document paths (PDF, DOCX, PPTX, XLSX). Uses docproc."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of paths to documents",
            },
            "max_chars_per_doc": {
                "type": "integer",
                "description": "Max chars to store per document (default 5000)",
            },
        },
        "required": ["file_paths"],
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        max_chars = kwargs.get("max_chars_per_doc", 5000)
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list of strings"
        if not isinstance(max_chars, int) or max_chars < 1:
            max_chars = 5000
        corpus = []
        errors = []
        for path in file_paths:
            if not isinstance(path, str) or not path.strip():
                continue
            p = Path(path.strip()).resolve()
            if not p.exists() or not p.is_file():
                errors.append(f"{path}: not found")
                continue
            if p.suffix.lower() not in DOCPROC_EXTENSIONS:
                errors.append(f"{path}: unsupported format")
                continue
            content, err = run_docproc_to_markdown(str(p))
            if err:
                errors.append(f"{path}: {err}")
                continue
            excerpt = (content or "").strip()[:max_chars]
            corpus.append({"path": str(p), "length": len(content or ""), "excerpt_length": len(excerpt)})
        result = {"documents": len(corpus), "corpus": corpus}
        if errors:
            result["errors"] = errors
        return json.dumps(result, indent=2)


register(CorpusBuilderTool())
