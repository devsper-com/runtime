"""Extract the surrounding context (sentence) for each citation in the text."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

CITE_PATTERNS = [
    re.compile(r"\([^)]*?\b(?:et\s+al\.?|&\s*[^)]+)[^)]*?\d{4}[^)]*\)", re.I),
    re.compile(r"\[\d+(?:\s*[-–,]\s*\d+)*\]"),
    re.compile(r"\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)"),
]


class CitationContextExtractorTool(Tool):
    """
    For each citation pattern found, extract the containing sentence as context.
    """

    name = "citation_context_extractor"
    description = "Extract the sentence context around each citation in a document."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "max_contexts": {"type": "integer", "description": "Max citation contexts (default 25)"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        max_contexts = kwargs.get("max_contexts", 25)
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        if not isinstance(max_contexts, int) or max_contexts < 1:
            max_contexts = 25
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        text = content or ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        results = []
        seen = set()
        for sent in sentences:
            for pat in CITE_PATTERNS:
                if pat.search(sent) and sent not in seen:
                    seen.add(sent)
                    results.append(sent.strip()[:400])
                    break
            if len(results) >= max_contexts:
                break
        if not results:
            return "No citation contexts found."
        return "Citation contexts:\n\n" + "\n\n".join(results)


register(CitationContextExtractorTool())
