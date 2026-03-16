"""Extract table-like content from docproc markdown (pipe tables)."""

import re
from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown


class ExtractTablesTool(Tool):
    """Extract markdown tables from document (docproc output)."""

    name = "extract_tables"
    description = "Extract tables from document as markdown. Uses docproc output."
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
        lines = content.splitlines()
        tables = []
        current = []
        in_table = False
        for line in lines:
            if "|" in line and line.strip().startswith("|"):
                current.append(line)
                in_table = True
            else:
                if in_table and current:
                    tables.append("\n".join(current))
                    current = []
                in_table = False
        if current:
            tables.append("\n".join(current))
        if not tables:
            return "No markdown tables found in extracted content."
        return "\n\n---\n\n".join(tables[:10])


register(ExtractTablesTool())
