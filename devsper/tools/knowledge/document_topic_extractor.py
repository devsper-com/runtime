"""Extract topic-like keywords from document text using frequency and stopword filtering."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown

STOP = frozenset(
    "a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that these those it its".split()
)


class DocumentTopicExtractorTool(Tool):
    """
    Extract candidate topics/keywords from a document using word frequency and stopword filtering.
    """

    name = "document_topic_extractor"
    description = "Extract topic keywords from a document (PDF, DOCX, etc.) via word frequency."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "top_n": {"type": "integer", "description": "Number of top topics (default 15)"},
            "min_length": {"type": "integer", "description": "Min word length (default 3)"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        top_n = kwargs.get("top_n", 15)
        min_length = kwargs.get("min_length", 3)
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        if not isinstance(top_n, int) or top_n < 1:
            top_n = 15
        if not isinstance(min_length, int) or min_length < 1:
            min_length = 3
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        text = (content or "").lower()
        words = re.findall(r"[a-z]+", text)
        counts = {}
        for w in words:
            if len(w) >= min_length and w not in STOP:
                counts[w] = counts.get(w, 0) + 1
        sorted_items = sorted(counts.items(), key=lambda x: -x[1])[:top_n]
        if not sorted_items:
            return "No topics extracted (empty or no matching words)."
        lines = [f"{word}: {count}" for word, count in sorted_items]
        return "Top topics (word: count):\n" + "\n".join(lines)


register(DocumentTopicExtractorTool())
