"""Compare methodology-related terms and sentences across multiple papers."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown

METHOD_WORDS = re.compile(
    r"\b(method|algorithm|model|framework|dataset|evaluation|training|accuracy|baseline|neural|transformer|embedding)\b",
    re.I,
)


class PaperMethodComparatorTool(Tool):
    """
    Compare methods across papers: shared methodology terms and per-paper method term counts.
    """

    name = "paper_method_comparator"
    description = "Compare methodology terms and sentences across multiple papers."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to papers",
            },
        },
        "required": ["file_paths"],
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list"
        doc_terms = {}
        all_terms = set()
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
            terms = list(dict.fromkeys(METHOD_WORDS.findall(text)))
            doc_terms[p.name] = [t.lower() for t in terms]
            all_terms.update(t.lower() for t in terms)
        shared = [t for t in all_terms if sum(1 for v in doc_terms.values() if t in v) > 1]
        lines = ["Method comparison", "=" * 40]
        for name, terms in doc_terms.items():
            lines.append(f"{name}: " + ", ".join(terms[:15]))
        lines.append("\nShared method terms: " + ", ".join(sorted(shared)))
        return "\n".join(lines)


register(PaperMethodComparatorTool())
