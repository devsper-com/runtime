"""
Knowledge graph: build relationships between stored memory.

Nodes: documents, concepts, datasets, methods.
Edges: mentions, cites, related_to, uses, extends, outperforms, constrains, blocks.
Uses networkx. v1.8: add_or_update_node, add_edge, save/load for extraction.
"""

import json
import os
import re
from typing import Any

import networkx as nx

from devsper.memory.memory_store import MemoryStore, get_default_store
from devsper.memory.memory_types import MemoryRecord, MemoryType


NODE_DOCUMENT = "document"
NODE_CONCEPT = "concept"
NODE_DATASET = "dataset"
NODE_METHOD = "method"

EDGE_MENTIONS = "mentions"
EDGE_CITES = "cites"
EDGE_RELATED_TO = "related_to"
EDGE_USES = "uses"
EDGE_EXTENDS = "extends"
EDGE_OUTPERFORMS = "outperforms"
EDGE_CONSTRAINS = "constrains"
EDGE_BLOCKS = "blocks"


def _extract_concepts(text: str, limit: int = 15) -> list[str]:
    """Heuristic: extract likely concepts (title-case phrases, known tokens)."""
    concepts = set()
    for m in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text):
        concepts.add(m.group(1).strip())
    tokens = re.findall(r"\b(diffusion|transformer|dataset|model|training|evaluation|baseline|embedding|neural)\b", text.lower())
    concepts.update(tokens)
    return list(concepts)[:limit]


def _extract_datasets(text: str, limit: int = 5) -> list[str]:
    """Heuristic: extract dataset-like names (e.g. MNIST, ImageNet)."""
    datasets = set()
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9\-]+(?:-\d+)?)\b", text):
        w = m.group(1)
        if len(w) >= 3 and w not in ("The", "This", "These", "When", "What"):
            datasets.add(w)
    return list(datasets)[:limit]


def _extract_methods(text: str, limit: int = 5) -> list[str]:
    """Heuristic: method-like phrases (e.g. 'X method', 'Y approach')."""
    methods = set()
    for m in re.finditer(r"(\w+(?:\s+\w+)?)\s+(?:method|approach|algorithm|framework)\b", text, re.IGNORECASE):
        methods.add(m.group(1).strip())
    return list(methods)[:limit]


class KnowledgeGraph:
    """
    Build and query a graph over memory: nodes are documents/concepts/datasets/methods,
    edges are mentions, cites, related_to.
    """

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or get_default_store()
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()

    def build_from_memory(self, merge: bool = False) -> nx.MultiDiGraph:
        """
        Build graph from all stored memory. Returns the graph.
        Nodes: document:<id>, concept:<name>, dataset:<name>, method:<name>.
        Edges: document --mentions--> concept/dataset/method; concept --related_to--> concept.
        If merge=True, add to existing graph instead of clearing (e.g. after load()).
        """
        if not merge:
            self._graph = nx.MultiDiGraph()
        records = self.store.list_memory(limit=2000)
        for r in records:
            doc_id = f"document:{r.id}"
            self._graph.add_node(doc_id, kind=NODE_DOCUMENT, memory_id=r.id, label=r.content[:200])
            for c in _extract_concepts(r.content):
                node = f"concept:{c}"
                self._graph.add_node(node, kind=NODE_CONCEPT, label=c)
                self._graph.add_edge(doc_id, node, type=EDGE_MENTIONS)
            for d in _extract_datasets(r.content):
                node = f"dataset:{d}"
                self._graph.add_node(node, kind=NODE_DATASET, label=d)
                self._graph.add_edge(doc_id, node, type=EDGE_MENTIONS)
            for m in _extract_methods(r.content):
                node = f"method:{m}"
                self._graph.add_node(node, kind=NODE_METHOD, label=m)
                self._graph.add_edge(doc_id, node, type=EDGE_MENTIONS)
        doc_nodes = [n for n, attrs in self._graph.nodes(data=True) if attrs.get("kind") == NODE_DOCUMENT]
        for doc in doc_nodes:
            succs = list(self._graph.successors(doc))
            concepts = [s for s in succs if s.startswith("concept:")]
            for i, a in enumerate(concepts):
                for b in concepts[i + 1 :]:
                    self._graph.add_edge(a, b, type=EDGE_RELATED_TO)
                    self._graph.add_edge(b, a, type=EDGE_RELATED_TO)
        return self._graph

    @property
    def graph(self) -> nx.MultiDiGraph:
        """Return the current graph (build first with build_from_memory if needed)."""
        return self._graph

    def get_neighbors(self, node_id: str, edge_type: str | None = None) -> list[tuple[str, str]]:
        """Return list of (neighbor_id, edge_type) for outgoing edges."""
        if node_id not in self._graph:
            return []
        out = []
        for _, v, data in self._graph.out_edges(node_id, data=True):
            et = data.get("type", "")
            if edge_type is None or et == edge_type:
                out.append((v, et))
        return out

    def get_documents_mentioning(self, concept_or_dataset: str) -> list[str]:
        """Return memory ids of documents that mention the given concept or dataset."""
        node = f"concept:{concept_or_dataset}"
        if node not in self._graph:
            node = f"dataset:{concept_or_dataset}"
        if node not in self._graph:
            return []
        doc_ids = []
        for pred in self._graph.predecessors(node):
            if pred.startswith("document:"):
                doc_ids.append(self._graph.nodes[pred].get("memory_id", pred.replace("document:", "")))
        return doc_ids

    def add_or_update_node(self, node_id: str, kind: str, label: str, **attrs: Any) -> None:
        """v1.8: Add or update a node (e.g. from KnowledgeExtractor)."""
        self._graph.add_node(node_id, kind=kind, label=label, **attrs)

    def add_edge(self, from_id: str, to_id: str, edge_type: str) -> None:
        """v1.8: Add a directed edge (e.g. from KnowledgeExtractor)."""
        self._graph.add_node(from_id, **self._graph.nodes.get(from_id, {}))
        self._graph.add_node(to_id, **self._graph.nodes.get(to_id, {}))
        self._graph.add_edge(from_id, to_id, type=edge_type)

    def _persist_path(self) -> str:
        """Path to persisted graph JSON (data_dir/knowledge_graph.json)."""
        try:
            from devsper.config import get_config
            base = get_config().data_dir
        except Exception:
            base = os.environ.get("DEVSPER_DATA_DIR", ".devsper")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "knowledge_graph.json")

    def save(self) -> None:
        """v1.8: Persist graph to JSON (nodes and edges only; no embeddings)."""
        nodes = []
        for nid, data in self._graph.nodes(data=True):
            nodes.append({"id": nid, **{k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))}})
        edges = []
        for u, v, data in self._graph.edges(data=True):
            edges.append({"from": u, "to": v, "type": data.get("type", "related_to")})
        payload = {"nodes": nodes, "edges": edges}
        with open(self._persist_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=0)

    def load(self) -> bool:
        """v1.8: Load graph from JSON if file exists; merge into _graph. Returns True if loaded."""
        path = self._persist_path()
        if not os.path.isfile(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        for n in payload.get("nodes", []):
            nid = n.pop("id", None)
            if nid:
                self._graph.add_node(nid, **n)
        for e in payload.get("edges", []):
            u, v = e.get("from"), e.get("to")
            if u and v:
                self._graph.add_edge(u, v, type=e.get("type", "related_to"))
        return True
