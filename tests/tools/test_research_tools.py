"""Tests for research tools."""

import pytest

from devsper.tools.research.wikipedia_lookup import WikipediaLookupTool
from devsper.tools.research.paper_summarizer import PaperSummarizerTool
from devsper.tools.research.citation_extractor import CitationExtractorTool
from devsper.tools.research.topic_cluster import TopicClusterTool
from devsper.tools.research.research_question_generator import ResearchQuestionGeneratorTool
from devsper.tools.research.paper_metadata_extractor import PaperMetadataExtractorTool


def test_wikipedia_lookup():
    out = WikipediaLookupTool().run(topic="Python (programming language)")
    assert "python" in out.lower() or "programming" in out.lower() or "No" in out


def test_paper_summarizer():
    text = "This is a long abstract. " * 50
    out = PaperSummarizerTool().run(text=text, max_chars=100)
    assert "Summary" in out and "Key" in out


def test_citation_extractor():
    text = "See Smith et al. (2020) and [1] for details."
    out = CitationExtractorTool().run(text=text)
    assert "2020" in out or "[1]" in out or "citation" in out.lower()


def test_topic_cluster():
    texts = ["machine learning algorithms", "deep learning models", "neural network training"]
    out = TopicClusterTool().run(texts=texts, top_n=5)
    assert "learning" in out.lower() or "network" in out.lower()


def test_research_question_generator():
    out = ResearchQuestionGeneratorTool().run(topic="climate change", count=2)
    assert "climate" in out.lower() and "?" in out


def test_paper_metadata_extractor():
    text = 'title = "My Paper" author = "Smith, J." year = "2021"'
    out = PaperMetadataExtractorTool().run(text=text)
    assert "My Paper" in out or "Smith" in out or "2021" in out
