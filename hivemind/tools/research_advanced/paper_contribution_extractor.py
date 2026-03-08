"""Extract contribution-like statements from paper text (we propose, our contribution, etc.)."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

CONTRIBUTION_PAT = re.compile(
    r"[^.!?]*(?:we\s+propose|our\s+contribution|this\s+paper\s+(?:presents|introduces|shows)|we\s+introduce|we\s+present|we\s+show|main\s+contribution)[^.!?]*[.!?]",
    re.I,
)


class PaperContributionExtractorTool(Tool):
    """
    Extract sentences that state contributions (we propose, our contribution, this paper presents, etc.).
    """

    name = "paper_contribution_extractor"
    description = "Extract contribution statements from a paper."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "max_sentences": {"type": "integer", "description": "Max sentences (default 15)"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        max_sentences = kwargs.get("max_sentences", 15)
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        if not isinstance(max_sentences, int) or max_sentences < 1:
            max_sentences = 15
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        text = content or ""
        matches = CONTRIBUTION_PAT.findall(text)
        selected = [m.strip()[:400] for m in matches[:max_sentences]]
        if not selected:
            return "No contribution sentences found (look for 'we propose', 'our contribution', etc.)."
        return "Contribution statements:\n\n" + "\n\n".join(selected)


register(PaperContributionExtractorTool())
