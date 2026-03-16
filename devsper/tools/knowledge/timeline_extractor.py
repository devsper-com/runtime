"""Extract date/time mentions from document text to build a simple timeline."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown

YEAR_PAT = re.compile(r"\b(19\d{2}|20\d{2})\b")
MONTHS = "january february march april may june july august september october november december".split()
MONTH_PAT = re.compile(r"\b(" + "|".join(MONTHS) + r")\s*,?\s*(19\d{2}|20\d{2})?", re.I)


class TimelineExtractorTool(Tool):
    """
    Extract date and year mentions from a document to produce a simple timeline.
    """

    name = "timeline_extractor"
    description = "Extract dates and years from a document to build a timeline."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "max_entries": {"type": "integer", "description": "Max timeline entries (default 30)"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        max_entries = kwargs.get("max_entries", 30)
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        if not isinstance(max_entries, int) or max_entries < 1:
            max_entries = 30
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        text = content or ""
        years = list(dict.fromkeys(YEAR_PAT.findall(text)))
        month_matches = list(dict.fromkeys(MONTH_PAT.findall(text)))
        timeline = []
        for y in sorted(years, key=int):
            timeline.append({"type": "year", "value": y})
        for m in month_matches:
            month = m[0].lower()
            year = m[1] if len(m) > 1 and m[1] else None
            timeline.append({"type": "month", "value": f"{month} {year or ''}".strip()})
        timeline = timeline[:max_entries]
        if not timeline:
            return "No dates or years found in the document."
        import json

        return json.dumps({"timeline": timeline}, indent=2)


register(TimelineExtractorTool())
