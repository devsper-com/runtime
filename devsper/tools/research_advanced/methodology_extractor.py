"""Extract methodology-related sentences from paper text using keyword heuristics."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown

METHOD_KEYWORDS = re.compile(
    r"\b(method|methods|methodology|experiment|dataset|evaluation|approach|algorithm|framework|procedure|protocol|design|implementation|training|model)\b",
    re.I,
)


class MethodologyExtractorTool(Tool):
    """
    Extract sentences that likely describe methodology (method, experiment, dataset, etc.).
    """

    name = "methodology_extractor"
    description = "Extract methodology-related sentences from a paper (PDF, DOCX, etc.)."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "max_sentences": {"type": "integer", "description": "Max sentences (default 20)"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        max_sentences = kwargs.get("max_sentences", 20)
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        if not isinstance(max_sentences, int) or max_sentences < 1:
            max_sentences = 20
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        text = content or ""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        selected = []
        for s in sentences:
            s = s.strip()
            if len(s) < 20:
                continue
            if METHOD_KEYWORDS.search(s):
                selected.append(s[:500])
                if len(selected) >= max_sentences:
                    break
        if not selected:
            return "No methodology sentences found (look for method/experiment/dataset/evaluation)."
        return "Methodology sentences:\n\n" + "\n\n".join(selected)


register(MethodologyExtractorTool())
