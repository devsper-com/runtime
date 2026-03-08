"""Analyze trends in papers by extracting years and term frequency over time (by document)."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

YEAR_PAT = re.compile(r"\b(19\d{2}|20\d{2})\b")
STOP = frozenset("a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that it its".split())


class PaperTrendAnalyzerTool(Tool):
    """
    Extract publication years from documents and aggregate term frequency by year (filename or content).
    """

    name = "paper_trend_analyzer"
    description = "Analyze trends: years and term frequency across papers."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to papers",
            },
            "top_terms": {"type": "integer", "description": "Top N terms overall (default 15)"},
        },
        "required": ["file_paths"],
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        top_terms = kwargs.get("top_terms", 15)
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list"
        if not isinstance(top_terms, int) or top_terms < 1:
            top_terms = 15
        year_to_terms = {}
        global_count = {}
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
            years = YEAR_PAT.findall(text)
            year = years[0] if years else "unknown"
            if year not in year_to_terms:
                year_to_terms[year] = []
            words = [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in STOP]
            from collections import Counter

            year_to_terms[year].extend(words)
            for w in words:
                global_count[w] = global_count.get(w, 0) + 1
        sorted_terms = sorted(global_count.items(), key=lambda x: -x[1])[:top_terms]
        lines = ["Trend analysis", "=" * 40, "Documents by year: " + ", ".join(sorted(year_to_terms.keys()))]
        lines.append("Global top terms: " + ", ".join(t for t, _ in sorted_terms))
        return "\n".join(lines)


register(PaperTrendAnalyzerTool())
