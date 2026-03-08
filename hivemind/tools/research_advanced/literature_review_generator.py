"""Generate a structured literature review outline from multiple paper abstracts or texts."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

STOP = frozenset("a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that it its".split())


class LiteratureReviewGeneratorTool(Tool):
    """
    Produce a literature review structure: common themes, key terms, and doc summaries from multiple papers.
    """

    name = "literature_review_generator"
    description = "Generate a structured literature review from multiple paper texts or document paths."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to papers (PDF, DOCX, etc.)",
            },
            "texts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Alternatively, raw text/abstracts",
            },
            "top_themes": {"type": "integer", "description": "Number of theme keywords (default 15)"},
        },
        "required": [],
    }

    def _get_texts(self, file_paths: list | None, texts: list | None) -> list[str]:
        out = []
        if texts and isinstance(texts, list):
            for t in texts:
                if isinstance(t, str) and t.strip():
                    out.append(t.strip())
        if file_paths and isinstance(file_paths, list):
            for path in file_paths:
                if not isinstance(path, str) or not path.strip():
                    continue
                content, err = run_docproc_to_markdown(path.strip())
                if not err and content:
                    out.append(content.strip())
        return out

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        texts = kwargs.get("texts")
        top_themes = kwargs.get("top_themes", 15)
        if not isinstance(top_themes, int) or top_themes < 1:
            top_themes = 15
        all_texts = self._get_texts(file_paths, texts)
        if not all_texts:
            return "Error: provide file_paths or texts (non-empty)"
        combined = " ".join(all_texts).lower()
        words = [w for w in re.findall(r"[a-z]+", combined) if len(w) >= 4 and w not in STOP]
        from collections import Counter

        counts = Counter(words)
        themes = [w for w, _ in counts.most_common(top_themes)]
        lines = [
            "Literature review outline",
            "=" * 40,
            "Common themes (keywords): " + ", ".join(themes),
            "",
            f"Documents/sources: {len(all_texts)}",
            "Per-source length (chars): " + ", ".join(str(len(t)) for t in all_texts),
        ]
        return "\n".join(lines)


register(LiteratureReviewGeneratorTool())
