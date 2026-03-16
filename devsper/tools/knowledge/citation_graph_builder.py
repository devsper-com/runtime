"""Build a citation graph from document text: extract citations and link doc -> refs."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown

CITE_PATTERNS = [
    re.compile(r"\([^)]*?\b(?:et\s+al\.?|&\s*[^)]+)[^)]*?\d{4}[^)]*\)", re.I),
    re.compile(r"\[\d+(?:\s*[-–,]\s*\d+)*\]"),
    re.compile(r"\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)"),
]


class CitationGraphBuilderTool(Tool):
    """
    Build a simple citation graph from multiple documents: nodes are docs, edges are citation refs.
    """

    name = "citation_graph_builder"
    description = "Build a citation graph from documents: extract citations and doc-to-ref links."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of paths to documents",
            },
        },
        "required": ["file_paths"],
    }

    def _extract_citations(self, text: str) -> list[str]:
        refs = []
        for pat in CITE_PATTERNS:
            refs.extend(pat.findall(text))
        return list(dict.fromkeys(refs))

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list of strings"
        nodes = []
        edges = []
        for path in file_paths:
            if not isinstance(path, str) or not path.strip():
                continue
            p = Path(path.strip()).resolve()
            if not p.exists() or not p.is_file():
                continue
            content, err = run_docproc_to_markdown(str(p))
            if err:
                continue
            text = content or ""
            name = p.name
            nodes.append(name)
            refs = self._extract_citations(text)
            for ref in refs:
                edges.append({"from": name, "citation": ref})
        result = {"nodes": nodes, "edges": edges, "edge_count": len(edges)}
        import json

        return json.dumps(result, indent=2)


register(CitationGraphBuilderTool())
