"""Tests for knowledge graph building."""
import os
import tempfile

import pytest
import networkx as nx

from devsper.memory.memory_store import MemoryStore, generate_memory_id
from devsper.memory.memory_index import MemoryIndex
from devsper.memory.memory_types import MemoryRecord, MemoryType
from devsper.knowledge.knowledge_graph import KnowledgeGraph


@pytest.fixture
def store_with_content():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = MemoryStore(db_path=path)
    index = MemoryIndex(s)
    r = MemoryRecord(
        id=generate_memory_id(),
        memory_type=MemoryType.RESEARCH,
        content="We compare the diffusion model with the transformer approach. The MNIST dataset was used. Our method achieves 90% accuracy.",
        tags=[],
    )
    r = index.ensure_embedding(r)
    s.store(r)
    yield s
    try:
        os.unlink(path)
    except Exception:
        pass


def test_build_from_memory(store_with_content):
    kg = KnowledgeGraph(store=store_with_content)
    g = kg.build_from_memory()
    assert isinstance(g, nx.MultiDiGraph)
    assert g.number_of_nodes() >= 1
    kinds = [d.get("kind") for _, d in g.nodes(data=True)]
    assert "document" in kinds


def test_get_documents_mentioning(store_with_content):
    kg = KnowledgeGraph(store=store_with_content)
    kg.build_from_memory()
    docs = kg.get_documents_mentioning("transformer")
    assert isinstance(docs, list)
