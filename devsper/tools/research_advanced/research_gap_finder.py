"""Identify potential research gaps by comparing question-like sentences and missing terms across papers."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown

STOP = frozenset("a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that it its we they".split())


class ResearchGapFinderTool(Tool):
    """
    Suggest research gaps: question phrases in papers and terms that appear in few documents.
    """

    name = "research_gap_finder"
    description = "Identify potential research gaps from question phrases and rare terms across papers."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to papers",
            },
            "min_doc_freq": {"type": "integer", "description": "Term in fewer than N docs = gap candidate (default 2)"},
        },
        "required": ["file_paths"],
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        min_doc_freq = kwargs.get("min_doc_freq", 2)
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list"
        if not isinstance(min_doc_freq, int) or min_doc_freq < 1:
            min_doc_freq = 2
        question_pat = re.compile(r"[^.!?]*\?+[^.!?]*")
        doc_terms = []
        all_questions = []
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
            questions = question_pat.findall(text)
            all_questions.extend(q.strip()[:100] for q in questions if len(q.strip()) > 10)
            words = {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in STOP}
            doc_terms.append((p.name, words))
        term_doc_count = {}
        for _, words in doc_terms:
            for w in words:
                term_doc_count[w] = term_doc_count.get(w, 0) + 1
        gap_terms = [w for w, c in term_doc_count.items() if c < min_doc_freq][:20]
        lines = ["Research gap indicators", "=" * 40]
        if all_questions:
            lines.append("Question phrases (research questions):")
            for q in all_questions[:10]:
                lines.append(f"  - {q}")
        lines.append("\nRare terms (in few documents): " + ", ".join(gap_terms[:15]))
        return "\n".join(lines)


register(ResearchGapFinderTool())
