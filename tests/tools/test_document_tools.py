"""Tests for document tools (docproc). When docproc is not installed, tools return a message."""

import tempfile
from pathlib import Path

import pytest

from hivemind.tools.documents.extract_document_text import ExtractDocumentTextTool
from hivemind.tools.documents.document_to_markdown import DocumentToMarkdownTool
from hivemind.tools.documents.summarize_document import SummarizeDocumentTool


def test_extract_document_text_nonexistent():
    out = ExtractDocumentTextTool().run(file_path="/nonexistent/doc.pdf")
    assert "not found" in out.lower() or "error" in out.lower()


def test_extract_document_text_unsupported_format():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        path = f.name
    try:
        out = ExtractDocumentTextTool().run(file_path=path)
        assert "unsupported" in out.lower() or "error" in out.lower() or "not found" in out.lower()
    finally:
        Path(path).unlink(missing_ok=True)


def test_summarize_document_invalid_path():
    out = SummarizeDocumentTool().run(file_path="/nonexistent/x.pdf")
    assert "error" in out.lower() or "not found" in out.lower() or "docproc" in out.lower()
