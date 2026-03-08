"""Summarize document by truncating docproc markdown (first N chars + key sentences)."""

import re
from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown


class SummarizeDocumentTool(Tool):
    """Produce a short summary of a document: first 500 chars and first 3 sentences. No LLM."""

    name = "summarize_document"
    description = "Summarize document (heuristic: first N chars and first sentences). Uses docproc."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "max_chars": {"type": "integer", "description": "Max chars in summary (default 500)"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        max_chars = kwargs.get("max_chars", 500)
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        if not isinstance(max_chars, int) or max_chars < 1:
            max_chars = 500
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        content = content.strip()
        if not content:
            return "(no content)"
        head = content[:max_chars] + ("..." if len(content) > max_chars else "")
        sentences = re.split(r"(?<=[.!?])\s+", content)
        first = " ".join(sentences[:3]) if sentences else head
        return f"Summary (first {max_chars} chars):\n{head}\n\nKey sentences:\n{first}"


register(SummarizeDocumentTool())
