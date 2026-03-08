"""Analyze concept (word) frequency across multiple documents."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

STOP = frozenset(
    "a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that these those it its i we they".split()
)


class ConceptFrequencyAnalyzerTool(Tool):
    """
    Compute concept (word) frequency across a corpus and return global and per-doc stats.
    """

    name = "concept_frequency_analyzer"
    description = "Analyze concept/word frequency across multiple documents."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of paths to documents",
            },
            "top_n": {"type": "integer", "description": "Top N concepts (default 20)"},
            "min_word_length": {"type": "integer", "description": "Min concept length (default 4)"},
        },
        "required": ["file_paths"],
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        top_n = kwargs.get("top_n", 20)
        min_len = kwargs.get("min_word_length", 4)
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list of strings"
        if not isinstance(top_n, int) or top_n < 1:
            top_n = 20
        if not isinstance(min_len, int) or min_len < 1:
            min_len = 4
        global_counts = {}
        doc_counts = []
        for path in file_paths:
            if not isinstance(path, str) or not path.strip():
                continue
            p = Path(path.strip()).resolve()
            if not p.exists() or not p.is_file():
                continue
            content, err = run_docproc_to_markdown(str(p))
            if err:
                continue
            text = (content or "").lower()
            words = [w for w in re.findall(r"[a-z]+", text) if len(w) >= min_len and w not in STOP]
            local = {}
            for w in words:
                local[w] = local.get(w, 0) + 1
                global_counts[w] = global_counts.get(w, 0) + 1
            doc_counts.append({"path": p.name, "concepts": len(local), "total_tokens": len(words)})
        sorted_global = sorted(global_counts.items(), key=lambda x: -x[1])[:top_n]
        lines = ["Global top concepts (concept: count):"]
        for w, c in sorted_global:
            lines.append(f"  {w}: {c}")
        lines.append("\nPer-document concept counts:")
        for d in doc_counts:
            lines.append(f"  {d['path']}: {d['concepts']} concepts, {d['total_tokens']} tokens")
        return "\n".join(lines)


register(ConceptFrequencyAnalyzerTool())
