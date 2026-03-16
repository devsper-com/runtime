"""Extract image references/descriptions from docproc markdown output."""

import re
from pathlib import Path

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown


class ExtractDocumentImagesTool(Tool):
    """Extract image blocks (markdown image syntax or alt text) from document via docproc."""

    name = "extract_document_images"
    description = "Extract image references and descriptions from document (docproc markdown)."
    input_schema = {
        "type": "object",
        "properties": {"file_path": {"type": "string", "description": "Path to the document"}},
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        images = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", content)
        if not images:
            alt_lines = re.findall(r"(?m)^.*[Ii]mage[^:\n]*:\s*.+$", content)
            if alt_lines:
                return "Image descriptions:\n" + "\n".join(alt_lines[:20])
            return "No image blocks found in extracted markdown. Docproc may embed images as text descriptions."
        lines = [f"alt: {a}\nurl: {u}" for a, u in images[:30]]
        return "\n---\n".join(lines)


register(ExtractDocumentImagesTool())
