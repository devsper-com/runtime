"""Build a knowledge graph from research documents: entities, citations, methods, datasets."""

import json
import re
from devsper.tools.base import Tool
from devsper.tools.registry import register

ENTITY_PATTERN = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b")
CITE_PATTERN = re.compile(r"\[[\d\s,–-]+\]|\([A-Z][a-z]+(?:\s+et\s+al\.?)?,?\s*\d{4}\)")
METHOD_PATTERN = re.compile(r"\b(?:method|approach|algorithm|model|framework|technique)s?\s+[:\s]+([^.!?\n]{10,80})", re.I)
DATASET_PATTERN = re.compile(r"\b(?:dataset|corpus|benchmark)s?\s+[:\s]*([A-Za-z0-9\-]+(?:\s+[A-Za-z0-9\-]+)*)", re.I)


def _extract_entities(text: str, max_n: int = 100) -> list[str]:
    candidates = ENTITY_PATTERN.findall(text)
    seen = set()
    out = []
    for c in candidates:
        c = c.strip()
        if len(c) > 2 and c not in seen and not c.isdigit():
            seen.add(c)
            out.append(c)
            if len(out) >= max_n:
                break
    return out


def _extract_citations(text: str, max_n: int = 50) -> list[str]:
    return list(dict.fromkeys(CITE_PATTERN.findall(text)))[:max_n]


def _extract_methods(text: str, max_n: int = 30) -> list[str]:
    return [m.group(1).strip()[:80] for m in METHOD_PATTERN.finditer(text)][:max_n]


def _extract_datasets(text: str, max_n: int = 20) -> list[str]:
    return [m.group(1).strip() for m in DATASET_PATTERN.finditer(text)][:max_n]


class ResearchGraphBuilderTool(Tool):
    """
    Build a graph of research knowledge from documents: entities, citations, methods, datasets.
    Output: nodes, edges, entity types (knowledge graph JSON).
    """

    name = "research_graph_builder"
    description = "Build a knowledge graph from research documents: extract entities, citations, methods, datasets."
    input_schema = {
        "type": "object",
        "properties": {
            "documents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of document texts to analyze",
            },
        },
        "required": ["documents"],
    }

    def run(self, **kwargs) -> str:
        documents = kwargs.get("documents")
        if not documents or not isinstance(documents, list):
            return "Error: documents must be a non-empty list of strings"
        texts = [d for d in documents if isinstance(d, str) and d.strip()][:50]
        if not texts:
            return "Error: no valid document strings provided"

        nodes = []
        edges = []
        entity_types = {}

        for i, text in enumerate(texts):
            doc_id = f"doc_{i}"
            nodes.append({"id": doc_id, "type": "document"})
            entities = _extract_entities(text)
            for e in entities:
                nid = f"entity_{e.replace(' ', '_')[:40]}"
                if not any(n["id"] == nid for n in nodes):
                    nodes.append({"id": nid, "type": "entity", "label": e})
                    entity_types[nid] = "entity"
                edges.append({"source": doc_id, "target": nid, "type": "mentions"})

            for c in _extract_citations(text):
                cid = f"cite_{hash(c) % 10**8}"
                nodes.append({"id": cid, "type": "citation", "label": c[:60]})
                edges.append({"source": doc_id, "target": cid, "type": "cites"})

            for m in _extract_methods(text):
                mid = f"method_{hash(m) % 10**8}"
                nodes.append({"id": mid, "type": "method", "label": m[:80]})
                entity_types[mid] = "method"
                edges.append({"source": doc_id, "target": mid, "type": "describes_method"})

            for d in _extract_datasets(text):
                did = f"dataset_{d.replace(' ', '_')[:30]}"
                if not any(n["id"] == did for n in nodes):
                    nodes.append({"id": did, "type": "dataset", "label": d})
                    entity_types[did] = "dataset"
                edges.append({"source": doc_id, "target": did, "type": "uses_dataset"})

        by_id = {n["id"]: n for n in nodes}
        nodes = list(by_id.values())

        return json.dumps({
            "nodes": nodes,
            "edges": edges,
            "entity_types": entity_types,
        }, indent=2)


register(ResearchGraphBuilderTool())
