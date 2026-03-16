"""Tests for knowledge pipeline tools."""

import json
import tempfile
from pathlib import Path

import pytest

from devsper.tools.knowledge.corpus_builder import CorpusBuilderTool
from devsper.tools.knowledge.document_corpus_summary import DocumentCorpusSummaryTool
from devsper.tools.knowledge.document_topic_extractor import DocumentTopicExtractorTool
from devsper.tools.knowledge.citation_graph_builder import CitationGraphBuilderTool
from devsper.tools.knowledge.concept_frequency_analyzer import ConceptFrequencyAnalyzerTool
from devsper.tools.knowledge.timeline_extractor import TimelineExtractorTool
from devsper.tools.knowledge.cross_document_entity_linker import CrossDocumentEntityLinkerTool
from devsper.tools.knowledge.knowledge_graph_extractor import KnowledgeGraphExtractorTool


def test_knowledge_graph_extractor_invalid_path():
    out = KnowledgeGraphExtractorTool().run(file_path="/nonexistent/doc.pdf")
    assert "Error" in out or "not found" in out.lower() or "docproc" in out.lower()


def test_corpus_builder_invalid_input():
    out = CorpusBuilderTool().run(file_paths=[])
    assert "Error" in out


def test_corpus_builder_nonexistent_paths():
    out = CorpusBuilderTool().run(file_paths=["/nonexistent/a.pdf", "/nonexistent/b.docx"])
    data = json.loads(out)
    assert "documents" in data
    assert data["documents"] == 0 or "errors" in data


def test_document_corpus_summary_no_input():
    out = DocumentCorpusSummaryTool().run()
    assert "Error" in out


def test_document_topic_extractor_invalid_path():
    out = DocumentTopicExtractorTool().run(file_path="/nonexistent/doc.pdf")
    assert "Error" in out or "not found" in out.lower() or "docproc" in out.lower()


def test_citation_graph_builder_empty():
    out = CitationGraphBuilderTool().run(file_paths=[])
    assert "Error" in out


def test_concept_frequency_analyzer_empty():
    out = ConceptFrequencyAnalyzerTool().run(file_paths=[])
    assert "Error" in out


def test_timeline_extractor_invalid_path():
    out = TimelineExtractorTool().run(file_path="/nonexistent/doc.pdf")
    assert "Error" in out or "not found" in out.lower() or "docproc" in out.lower()


def test_cross_document_entity_linker_empty():
    out = CrossDocumentEntityLinkerTool().run(file_paths=[])
    assert "Error" in out
