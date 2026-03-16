"""
v1.8: Post-run knowledge extraction from task results into the knowledge graph.
Heuristic extraction (no LLM); fast, non-blocking.
"""

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from devsper.knowledge.knowledge_graph import (
    KnowledgeGraph,
    NODE_CONCEPT,
    NODE_DATASET,
    NODE_DOCUMENT,
    NODE_METHOD,
    EDGE_USES,
    EDGE_EXTENDS,
    EDGE_OUTPERFORMS,
    EDGE_CITES,
)
from devsper.types.task import Task, TaskStatus
from devsper.types.event import Event, events


@dataclass
class KGNode:
    """Lightweight node for extractor output."""
    id: str
    kind: str
    label: str
    confidence: float


@dataclass
class KGEdge:
    """Lightweight edge for extractor output."""
    from_id: str
    to_id: str
    edge_type: str


# Patterns for documents: explicit citations
_DOC_PATTERN = re.compile(
    r"(?:according to|paper:|article:|from)\s*[:\s]*([^\n.]+?)(?:\.|$)|(https?://[^\s]+)",
    re.IGNORECASE,
)
# Capitalized multi-word (2-3 words)
_CONCEPT_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z0-9]+){1,2})\b")
# Technical: digits+letters, camelCase
_TECH_PATTERN = re.compile(r"\b([a-z]+[A-Z][a-zA-Z0-9]*|[A-Z][a-z]+[A-Z][a-zA-Z0-9]*)\b")
# Dataset/corpus/benchmark near a proper noun
_DATASET_PATTERN = re.compile(
    r"\b(dataset|corpus|benchmark)\s+[\[']?([A-Za-z0-9\-_]+)[\]']?|\b([A-Z][A-Za-z0-9\-]+(?:-\d+)?)\s+(?:dataset|corpus|benchmark)\b",
    re.IGNORECASE,
)
# "using X", "via X", "with X" method
_METHOD_PATTERN = re.compile(
    r"\b(?:using|via|with)\s+([A-Z][A-Za-z0-9\s]+?)(?:\s+to|\s+for|,|\.|$)",
    re.IGNORECASE,
)

# Relationship patterns (entity co-occurrence in same sentence)
_REL_USES = re.compile(r"(\w+(?:\s+\w+)?)\s+(?:uses?|leverages?)\s+(\w+(?:\s+\w+)?)", re.IGNORECASE)
_REL_EXTENDS = re.compile(r"(\w+(?:\s+\w+)?)\s+(?:is\s+based\s+on|extends?)\s+(\w+(?:\s+\w+)?)", re.IGNORECASE)
_REL_OUTPERFORMS = re.compile(r"(\w+(?:\s+\w+)?)\s+(?:outperforms?|is\s+better\s+than)\s+(\w+(?:\s+\w+)?)", re.IGNORECASE)
_REL_CITES = re.compile(r"(\w+(?:\s+\w+)?)\s+(?:cites?|references?)\s+(\w+(?:\s+\w+)?)", re.IGNORECASE)


def _normalize_id(kind: str, label: str) -> str:
    label_clean = re.sub(r"\s+", " ", label.strip())
    return f"{kind}:{label_clean}"


class KnowledgeExtractor:
    """
    Post-run background pass: extract entities, facts, and relationships
    from task results and add to knowledge graph.
    """

    def __init__(self, min_confidence: float = 0.60):
        self.min_confidence = min_confidence

    async def extract_from_run(
        self,
        run_id: str,
        tasks: list[Task],
        kg: KnowledgeGraph,
        event_log=None,
    ) -> None:
        """Called after SWARM_FINISHED. Run in background, non-blocking."""
        start = time.perf_counter()
        nodes_added = 0
        edges_added = 0
        for task in tasks:
            if task.status != TaskStatus.COMPLETED or not task.result:
                continue
            entities = self._extract_entities(task.result)
            for e in entities:
                if e.confidence >= self.min_confidence:
                    kg.add_or_update_node(e.id, e.kind, e.label, confidence=e.confidence)
                    nodes_added += 1
            relationships = self._extract_relationships(task.result, entities)
            for rel in relationships:
                kg.add_edge(rel.from_id, rel.to_id, rel.edge_type)
                edges_added += 1
        kg.save()
        duration = time.perf_counter() - start
        if event_log is not None:
            event_log.append_event(
                Event(
                    timestamp=datetime.now(timezone.utc),
                    type=events.KNOWLEDGE_EXTRACTED,
                    payload={
                        "run_id": run_id,
                        "nodes_added": nodes_added,
                        "edges_added": edges_added,
                        "duration_seconds": round(duration, 2),
                    },
                )
            )
        return None

    def _extract_entities(self, text: str) -> list[KGNode]:
        """Heuristic extraction. Confidence: URL/explicit 0.95, repeated 3+ 0.80, single 0.60."""
        if not text or not text.strip():
            return []
        nodes: list[KGNode] = []
        seen: dict[str, float] = {}

        # Documents: URLs, "According to", "paper:", "article:"
        for m in _DOC_PATTERN.finditer(text):
            g1, g2 = m.group(1), m.group(2)
            raw = (g1 or g2 or "").strip()
            if not raw:
                continue
            if raw.startswith("http"):
                node_id = _normalize_id(NODE_DOCUMENT, raw[:80])
                nodes.append(KGNode(id=node_id, kind=NODE_DOCUMENT, label=raw[:200], confidence=0.95))
            else:
                node_id = _normalize_id(NODE_DOCUMENT, raw[:100])
                nodes.append(KGNode(id=node_id, kind=NODE_DOCUMENT, label=raw[:200], confidence=0.95))

        # Concepts: capitalized phrases, technical terms
        sentences = re.split(r"[.!?]\s+", text)
        concept_mentions: dict[str, int] = {}
        for sent in sentences:
            for m in _CONCEPT_PATTERN.finditer(sent):
                c = m.group(1).strip()
                if len(c) < 3 or c.lower() in ("the", "this", "that"):
                    continue
                concept_mentions[c] = concept_mentions.get(c, 0) + 1
            for m in _TECH_PATTERN.finditer(sent):
                c = m.group(1).strip()
                if len(c) < 2:
                    continue
                concept_mentions[c] = concept_mentions.get(c, 0) + 1
        for label, count in concept_mentions.items():
            conf = 0.80 if count >= 3 else 0.60
            node_id = _normalize_id(NODE_CONCEPT, label)
            if node_id not in seen or seen[node_id] < conf:
                seen[node_id] = conf
                nodes.append(KGNode(id=node_id, kind=NODE_CONCEPT, label=label, confidence=conf))

        # Datasets
        for m in _DATASET_PATTERN.finditer(text):
            name = (m.group(2) or m.group(3) or "").strip()
            if name and len(name) >= 2:
                node_id = _normalize_id(NODE_DATASET, name)
                nodes.append(KGNode(id=node_id, kind=NODE_DATASET, label=name, confidence=0.75))

        # Methods: "using X", "via X"
        for m in _METHOD_PATTERN.finditer(text):
            name = m.group(1).strip()
            if len(name) >= 2:
                node_id = _normalize_id(NODE_METHOD, name)
                nodes.append(KGNode(id=node_id, kind=NODE_METHOD, label=name, confidence=0.70))

        return nodes

    def _extract_relationships(
        self,
        text: str,
        entities: list[KGNode],
    ) -> list[KGEdge]:
        """Typed edges between detected entities; pattern match on co-occurrence."""
        edges: list[KGEdge] = []
        entity_labels = {e.label.lower(): e for e in entities}
        entity_labels.update({e.id.split(":", 1)[-1].lower(): e for e in entities})

        def try_edge(pat: re.Pattern, edge_type: str) -> None:
            for m in pat.finditer(text):
                a, b = m.group(1).strip(), m.group(2).strip()
                a_lower, b_lower = a.lower(), b.lower()
                node_a = entity_labels.get(a_lower) or entity_labels.get(a)
                node_b = entity_labels.get(b_lower) or entity_labels.get(b)
                if node_a and node_b and node_a.id != node_b.id:
                    edges.append(KGEdge(from_id=node_a.id, to_id=node_b.id, edge_type=edge_type))

        try_edge(_REL_USES, EDGE_USES)
        try_edge(_REL_EXTENDS, EDGE_EXTENDS)
        try_edge(_REL_OUTPERFORMS, EDGE_OUTPERFORMS)
        try_edge(_REL_CITES, EDGE_CITES)
        return edges
