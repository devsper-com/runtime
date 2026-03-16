"""Convert document to markdown using docproc."""

from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.tools.documents._docproc import run_docproc_to_markdown


class DocumentToMarkdownTool(Tool):
    """Convert PDF, DOCX, PPTX, or XLSX to markdown via docproc. Returns the markdown content."""

    name = "document_to_markdown"
    description = "Convert document to markdown. Returns full markdown text."
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
        return content.strip() or "(empty markdown)"


register(DocumentToMarkdownTool())
