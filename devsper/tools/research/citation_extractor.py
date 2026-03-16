"""Extract citation-like patterns from text (e.g. Author et al. (Year), [1], etc.)."""

import re

from devsper.tools.base import Tool
from devsper.tools.registry import register


class CitationExtractorTool(Tool):
    """Extract citation-like patterns from text: (Author et al., 20XX), [1], etc."""

    name = "citation_extractor"
    description = "Extract citation patterns from text: (Author et al., year), [n], numbered refs."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text that may contain citations"}},
        "required": ["text"],
    }

    def run(self, **kwargs) -> str:
        text = kwargs.get("text")
        if text is None:
            return "Error: text is required"
        if not isinstance(text, str):
            text = str(text)
        paren = re.findall(r'\([^)]*?\b(?:et\s+al\.?|&\s*[^)]+)[^)]*?\d{4}[^)]*\)', text, re.I)
        bracket = re.findall(r'\[\d+(?:\s*[-–,]\s*\d+)*\]', text)
        author_year = re.findall(r'\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)', text)
        all_refs = list(dict.fromkeys(paren + bracket + author_year))
        if not all_refs:
            return "No citation patterns found."
        return "Extracted citations:\n" + "\n".join(all_refs)


register(CitationExtractorTool())
