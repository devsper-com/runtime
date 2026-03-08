"""Extract full text from a document (PDF, DOCX, etc.) using docproc."""

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown


class ExtractDocumentTextTool(Tool):
    """Extract all text from a document (PDF, DOCX, PPTX, XLSX) via docproc."""

    name = "extract_document_text"
    description = "Extract full text from PDF, DOCX, PPTX, or XLSX using docproc."
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
        return content.strip() or "(no text extracted)"


register(ExtractDocumentTextTool())
