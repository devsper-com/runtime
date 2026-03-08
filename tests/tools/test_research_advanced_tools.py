"""Tests for research advanced tools."""

import json
import pytest

from hivemind.tools.research_advanced.literature_review_generator import LiteratureReviewGeneratorTool
from hivemind.tools.research_advanced.paper_similarity_search import PaperSimilaritySearchTool
from hivemind.tools.research_advanced.research_gap_finder import ResearchGapFinderTool
from hivemind.tools.research_advanced.methodology_extractor import MethodologyExtractorTool
from hivemind.tools.research_advanced.paper_contribution_extractor import PaperContributionExtractorTool
from hivemind.tools.research_advanced.paper_dataset_identifier import PaperDatasetIdentifierTool
from hivemind.tools.research_advanced.research_topic_mapper import ResearchTopicMapperTool
from hivemind.tools.research_advanced.paper_trend_analyzer import PaperTrendAnalyzerTool
from hivemind.tools.research_advanced.paper_method_comparator import PaperMethodComparatorTool
from hivemind.tools.research_advanced.parallel_document_analyzer import ParallelDocumentAnalyzerTool
from hivemind.tools.research_advanced.swarm_literature_review import SwarmLiteratureReviewTool
from hivemind.tools.research_advanced.citation_context_extractor import CitationContextExtractorTool


def test_citation_context_extractor_invalid_path():
    out = CitationContextExtractorTool().run(file_path="/nonexistent/doc.pdf")
    assert "Error" in out or "not found" in out.lower() or "docproc" in out.lower()


def test_literature_review_generator_with_texts():
    out = LiteratureReviewGeneratorTool().run(texts=["Machine learning is used in NLP. Deep learning models.", "Neural networks and transformers."])
    assert "theme" in out.lower() or "Documents" in out


def test_literature_review_generator_no_input():
    out = LiteratureReviewGeneratorTool().run()
    assert "Error" in out


def test_paper_similarity_search_no_query():
    out = PaperSimilaritySearchTool().run(query="", file_paths=[])
    assert "Error" in out


def test_research_gap_finder_empty():
    out = ResearchGapFinderTool().run(file_paths=[])
    assert "Error" in out


def test_methodology_extractor_invalid_path():
    out = MethodologyExtractorTool().run(file_path="/nonexistent/doc.pdf")
    assert "Error" in out or "not found" in out.lower()


def test_paper_contribution_extractor_invalid_path():
    out = PaperContributionExtractorTool().run(file_path="/nonexistent/doc.pdf")
    assert "Error" in out or "not found" in out.lower()


def test_paper_dataset_identifier_invalid_path():
    out = PaperDatasetIdentifierTool().run(file_path="/nonexistent/doc.pdf")
    assert "Error" in out or "not found" in out.lower()


def test_research_topic_mapper_empty():
    out = ResearchTopicMapperTool().run(file_paths=[])
    assert "Error" in out


def test_paper_trend_analyzer_empty():
    out = PaperTrendAnalyzerTool().run(file_paths=[])
    assert "Error" in out


def test_paper_method_comparator_empty():
    out = PaperMethodComparatorTool().run(file_paths=[])
    assert "Error" in out


def test_parallel_document_analyzer_with_paths():
    out = ParallelDocumentAnalyzerTool().run(file_paths=["a.pdf", "b.pdf", "c.pdf"], batch_size=2)
    data = json.loads(out)
    assert data["total_documents"] == 3
    assert data["num_batches"] == 2
    assert "batches" in data


def test_parallel_document_analyzer_no_input():
    out = ParallelDocumentAnalyzerTool().run()
    assert "Error" in out


def test_swarm_literature_review():
    out = SwarmLiteratureReviewTool().run(texts=["First doc about ML.", "Second doc about NLP."], batch_size=1)
    data = json.loads(out)
    assert "batches" in data
    assert data["total_documents"] == 2
