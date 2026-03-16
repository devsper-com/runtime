"""Search for papers similar to a query text using simple term overlap (no embeddings)."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown

STOP = frozenset("a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that it its".split())


class PaperSimilaritySearchTool(Tool):
    """
    Rank documents by term-overlap similarity to a query (bag-of-words, no embeddings).
    """

    name = "paper_similarity_search"
    description = "Find documents most similar to a query text using term overlap."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query text or abstract"},
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to candidate documents",
            },
            "top_k": {"type": "integer", "description": "Number of results (default 5)"},
        },
        "required": ["query", "file_paths"],
    }

    def _tokens(self, text: str, min_len: int = 3) -> set[str]:
        words = re.findall(r"[a-z]+", text.lower())
        return {w for w in words if len(w) >= min_len and w not in STOP}

    def run(self, **kwargs) -> str:
        query = kwargs.get("query")
        file_paths = kwargs.get("file_paths")
        top_k = kwargs.get("top_k", 5)
        if not query or not isinstance(query, str):
            return "Error: query must be a non-empty string"
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list"
        if not isinstance(top_k, int) or top_k < 1:
            top_k = 5
        q_set = self._tokens(query)
        if not q_set:
            return "Error: query produced no tokens"
        scores = []
        for path in file_paths:
            if not isinstance(path, str) or not path.strip():
                continue
            p = Path(path.strip()).resolve()
            if not p.exists() or not p.is_file():
                continue
            content, err = run_docproc_to_markdown(str(p))
            if err:
                continue
            doc_set = self._tokens(content or "")
            overlap = len(q_set & doc_set) / len(q_set) if q_set else 0
            scores.append((p.name, overlap))
        scores.sort(key=lambda x: -x[1])
        result = [f"{name}: {score:.3f}" for name, score in scores[:top_k]]
        return "Similarity (term overlap):\n" + "\n".join(result) if result else "No documents processed."


register(PaperSimilaritySearchTool())
