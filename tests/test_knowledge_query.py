"""Tests for knowledge graph query."""

from hivemind.knowledge.knowledge_graph import KnowledgeGraph
from hivemind.knowledge.query import entity_search, query, QueryResult


def test_entity_search_empty_graph():
    """Empty graph returns no entities."""
    kg = KnowledgeGraph()
    kg._graph = kg.graph  # ensure empty
    matches = entity_search(kg, "diffusion")
    assert matches == []


def test_query_returns_result_structure():
    """query() returns QueryResult with entities, edges, documents."""
    kg = KnowledgeGraph()
    result = query(kg, "diffusion")
    assert isinstance(result, QueryResult)
    assert hasattr(result, "entities")
    assert hasattr(result, "edges")
    assert hasattr(result, "documents")
    assert isinstance(result.entities, list)
    assert isinstance(result.edges, list)
    assert isinstance(result.documents, list)
