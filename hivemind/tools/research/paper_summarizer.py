"""Summarize paper text by truncation and key sentence extraction heuristics."""

import re

from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class PaperSummarizerTool(Tool):
    """Produce a short summary of paper text (first N chars and first few sentences). No LLM."""

    name = "paper_summarizer"
    description = "Summarize paper/abstract text: first 500 chars and first 3 sentences."
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Paper abstract or body text"},
            "max_chars": {"type": "integer", "description": "Max characters in summary (default 500)"},
        },
        "required": ["text"],
    }

    def run(self, **kwargs) -> str:
        text = kwargs.get("text")
        max_chars = kwargs.get("max_chars", 500)
        if text is None:
            return "Error: text is required"
        if not isinstance(text, str):
            text = str(text)
        if not isinstance(max_chars, int) or max_chars < 1:
            max_chars = 500
        text = text.strip()
        if not text:
            return "Error: text is empty"
        head = text[:max_chars] + ("..." if len(text) > max_chars else "")
        sentences = re.split(r'(?<=[.!?])\s+', text)
        first_sentences = " ".join(sentences[:3]) if sentences else head
        return f"Summary (first {max_chars} chars):\n{head}\n\nKey sentences:\n{first_sentences}"


register(PaperSummarizerTool())
