"""Identify dataset names mentioned in paper text using common patterns."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

DATASET_PAT = re.compile(
    r"\b([A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*)\s+(?:dataset|benchmark|corpus)\b|\b(?:on|using|with)\s+([A-Z][A-Za-z0-9\-]+(?:\s+[A-Z][A-Za-z0-9\-]+)*)\s+(?:dataset|benchmark)?",
    re.I,
)


class PaperDatasetIdentifierTool(Tool):
    """
    Find dataset and benchmark names mentioned in a paper.
    """

    name = "paper_dataset_identifier"
    description = "Identify dataset and benchmark names mentioned in a paper."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        text = content or ""
        found = set()
        for m in DATASET_PAT.finditer(text):
            for g in m.groups():
                if g and len(g) > 1:
                    found.add(g.strip())
        if not found:
            return "No dataset/benchmark names identified (look for 'X dataset', 'on X', 'using X')."
        return "Datasets/benchmarks: " + ", ".join(sorted(found))


register(PaperDatasetIdentifierTool())
