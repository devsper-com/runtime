"""
Knowledge graph query: entity search and relationship traversal.
"""

from dataclasses import dataclass

from hivemind.knowledge.knowledge_graph import KnowledgeGraph, NODE_DOCUMENT


@dataclass
class QueryResult:
    """Structured result: entities matching query and edges (optionally traversed)."""

    entities: list[tuple[str, str]]  # (node_id, label)
    edges: list[tuple[str, str, str]]  # (from_id, to_id, edge_type)
    documents: list[str]  # memory ids of documents mentioning matched entities


def _node_matches_label(node_id: str, label: str, query_lower: str) -> bool:
    """True if node label or id contains query terms."""
    if not label:
        return False
    return query_lower in label.lower() or query_lower in node_id.lower()


def entity_search(kg: KnowledgeGraph, query_text: str) -> list[tuple[str, str]]:
    """
    Find nodes (concept, dataset, method) whose label matches the query.
    Returns list of (node_id, label).
    """
    query_lower = (query_text or "").strip().lower()
    if not query_lower:
        return []
    g = kg.graph
    matches: list[tuple[str, str]] = []
    for node_id, data in g.nodes(data=True):
        kind = data.get("kind")
        if kind in (NODE_DOCUMENT,):
            continue
        label = data.get("label", "") or node_id.split(":", 1)[-1] if ":" in node_id else node_id
        if _node_matches_label(node_id, label, query_lower):
            matches.append((node_id, label))
    return matches


def traverse(
    kg: KnowledgeGraph,
    node_ids: list[str],
    hops: int = 1,
    edge_type: str | None = None,
) -> list[tuple[str, str, str]]:
    """
    Traverse from given nodes up to `hops` steps. Returns list of (from_id, to_id, edge_type).
    """
    if hops < 1:
        return []
    g = kg.graph
    edges: list[tuple[str, str, str]] = []
    frontier = set(node_ids)
    seen_edges: set[tuple[str, str]] = set()
    for _ in range(hops):
        next_frontier = set()
        for n in frontier:
            if n not in g:
                continue
            for _, v, data in g.out_edges(n, data=True):
                et = data.get("type", "")
                if edge_type is not None and et != edge_type:
                    continue
                key = (n, v)
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append((n, v, et))
                next_frontier.add(v)
        frontier = next_frontier
    return edges


def query(
    kg: KnowledgeGraph,
    query_text: str,
    traverse_hops: int = 1,
) -> QueryResult:
    """
    Run entity search for query_text, optionally traverse relationships (1-2 hops).
    Returns QueryResult with entities, edges, and document ids.
    """
    entities = entity_search(kg, query_text)
    node_ids = [e[0] for e in entities]
    edges = traverse(kg, node_ids, hops=traverse_hops) if node_ids else []
    documents: list[str] = []
    for nid, _ in entities:
        if nid.startswith("document:"):
            continue
        concept_or_dataset = nid.split(":", 1)[-1] if ":" in nid else nid
        docs = kg.get_documents_mentioning(concept_or_dataset)
        documents.extend(docs)
    documents = list(dict.fromkeys(documents))
    return QueryResult(entities=entities, edges=edges, documents=documents)
