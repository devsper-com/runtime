"""Extract paper metadata (title, authors, year) from bib-like or plain text."""

import re

from devsper.tools.base import Tool
from devsper.tools.registry import register


class PaperMetadataExtractorTool(Tool):
    """Extract title, authors, and year from bib-like text or structured paragraphs."""

    name = "paper_metadata_extractor"
    description = "Extract title, authors, year from bib-style or plain text."
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Bib entry or text containing title/author/year"}},
        "required": ["text"],
    }

    def run(self, **kwargs) -> str:
        text = kwargs.get("text")
        if text is None:
            return "Error: text is required"
        if not isinstance(text, str):
            text = str(text)
        out = []
        title_match = re.search(r"title\s*=\s*[{\"]([^}\"]+)[}\"]", text, re.I)
        if title_match:
            out.append(f"Title: {title_match.group(1).strip()}")
        author_match = re.search(r"author\s*=\s*[{\"]([^}\"]+)[}\"]", text, re.I)
        if author_match:
            out.append(f"Authors: {author_match.group(1).strip()}")
        year_match = re.search(r"year\s*=\s*[\"]?(\d{4})[\"]?", text)
        if year_match:
            out.append(f"Year: {year_match.group(1)}")
        if not out and re.search(r"\d{4}", text):
            years = re.findall(r"\b(19\d{2}|20\d{2})\b", text)
            if years:
                out.append(f"Year: {years[0]}")
        if not out:
            return "No structured metadata found. Try bib-style or explicit title/author/year."
        return "\n".join(out)


register(PaperMetadataExtractorTool())
