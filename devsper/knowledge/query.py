"""
Knowledge graph query: entity search and relationship traversal.
v1.8: query_for_planning for knowledge-guided planning.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

from devsper.knowledge.knowledge_graph import (
    KnowledgeGraph,
    NODE_DOCUMENT,
    NODE_CONCEPT,
    NODE_DATASET,
    NODE_METHOD,
)


@dataclass
class QueryResult:
    """Structured result: entities matching query and edges (optionally traversed)."""

    entities: list[tuple[str, str]]  # (node_id, label)
    edges: list[tuple[str, str, str]]  # (from_id, to_id, edge_type)
    documents: list[str]  # memory ids of documents mentioning matched entities


@dataclass
class PlanningContext:
    """v1.8: Context from KG for planner injection."""

    relevant_concepts: list[str]
    prior_findings: list[str]
    known_constraints: list[str]
    related_methods: list[str]
    confidence: float


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


# Stopwords for task term extraction (simple heuristic)
_PLANNING_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "can", "this",
        "that", "these", "those", "it", "its", "into", "through", "during",
    }
)


def _extract_candidate_terms(task_description: str) -> list[str]:
    """Extract candidate terms: split on spaces, drop stopwords, keep capitalized or domain-like."""
    if not task_description or not task_description.strip():
        return []
    words = task_description.strip().split()
    candidates = []
    for w in words:
        w_clean = w.strip(".,;:!?").lower()
        if not w_clean or w_clean in _PLANNING_STOPWORDS:
            continue
        if w[0].isupper() or any(c.isdigit() for c in w) or "_" in w:
            candidates.append(w_clean)
        else:
            candidates.append(w_clean)
    return list(dict.fromkeys(candidates))


def _fuzzy_match_label(term: str, label: str, threshold: float = 0.8) -> float:
    """Return similarity ratio in [0, 1]; 0 if below threshold."""
    if not label:
        return 0.0
    label_lower = label.lower()
    term_lower = term.lower()
    if term_lower in label_lower:
        return min(1.0, 0.8 + 0.2 * (len(term_lower) / max(1, len(label_lower))))
    r = SequenceMatcher(None, term_lower, label_lower).ratio()
    return r if r >= threshold else 0.0


def query_for_planning(kg: KnowledgeGraph, task_description: str) -> PlanningContext:
    """
    Build planning context from KG: concepts, findings, constraints, methods.
    Uses term extraction, fuzzy node match, 2-hop neighborhood, centrality + match scoring.
    """
    concepts: list[str] = []
    findings: list[str] = []
    constraints: list[str] = []
    methods: list[str] = []
    g = kg.graph
    if g.number_of_nodes() == 0:
        return PlanningContext(
            relevant_concepts=[],
            prior_findings=[],
            known_constraints=[],
            related_methods=[],
            confidence=0.0,
        )

    terms = _extract_candidate_terms(task_description)
    matched_nodes: list[tuple[str, str, float]] = []  # (node_id, label, match_score)
    for node_id, data in g.nodes(data=True):
        kind = data.get("kind")
        if kind == NODE_DOCUMENT:
            continue
        label = data.get("label", "") or (node_id.split(":", 1)[-1] if ":" in node_id else node_id)
        for t in terms:
            score = _fuzzy_match_label(t, label, 0.8)
            if score > 0:
                matched_nodes.append((node_id, label, score))
                break

    if not matched_nodes:
        return PlanningContext(
            relevant_concepts=[],
            prior_findings=[],
            known_constraints=[],
            related_methods=[],
            confidence=0.0,
        )

    neighborhood = set(n[0] for n in matched_nodes)
    for _ in range(2):
        next_n = set()
        for nid in neighborhood:
            if nid not in g:
                continue
            for _, v, _ in g.out_edges(nid, data=True):
                next_n.add(v)
            for u, _, _ in g.in_edges(nid, data=True):
                next_n.add(u)
        neighborhood |= next_n

    match_scores: dict[str, float] = {}
    for nid, label, s in matched_nodes:
        match_scores[nid] = max(match_scores.get(nid, 0), s)
    try:
        degree = dict(g.degree(neighborhood))
    except Exception:
        degree = {n: 0 for n in neighborhood}
    scores: list[tuple[str, str, str, float]] = []
    for nid in neighborhood:
        data = g.nodes.get(nid, {})
        kind = data.get("kind", "")
        label = data.get("label", "") or (nid.split(":", 1)[-1] if ":" in nid else nid)
        deg = degree.get(nid, 0)
        recency = 1.0
        ms = match_scores.get(nid, 0.5)
        total = (deg * 0.3) + (recency * 0.2) + (ms * 0.5)
        scores.append((nid, kind, label, total))

    scores.sort(key=lambda x: -x[3])
    top = scores[:30]
    for nid, kind, label, _ in top:
        if kind == NODE_CONCEPT and label not in concepts:
            concepts.append(label)
        elif kind == NODE_METHOD and label not in methods:
            methods.append(label)

    for u, v, data in g.out_edges(neighborhood, data=True):
        if data.get("type") in ("constrains", "blocks"):
            edge_desc = f"{u.split(':', 1)[-1] if ':' in u else u} -> {v.split(':', 1)[-1] if ':' in v else v}"
            if edge_desc not in constraints:
                constraints.append(edge_desc)

    doc_nodes = [n for n in neighborhood if g.nodes.get(n, {}).get("kind") == NODE_DOCUMENT]
    for d in doc_nodes[:5]:
        summary = (g.nodes[d].get("label", "") or d)[:200]
        if summary and summary not in findings:
            findings.append(summary)

    total_nodes = g.number_of_nodes()
    found = len(concepts) + len(methods) + len(findings) + len(constraints)
    confidence = min(1.0, (found / max(1, total_nodes)) * 2.0) if total_nodes else 0.0
    confidence = max(0.0, min(1.0, confidence))

    return PlanningContext(
        relevant_concepts=concepts[:15],
        prior_findings=findings[:5],
        known_constraints=constraints[:10],
        related_methods=methods[:10],
        confidence=confidence,
    )


def format_planning_context(ctx: PlanningContext, max_tokens: int = 300) -> str:
    """Render PlanningContext as concise bullet list; only non-empty sections; prepend confidence."""
    parts = []
    if ctx.confidence >= 0.7:
        parts.append("High confidence")
    elif ctx.confidence >= 0.3:
        parts.append("Partial context")
    if ctx.relevant_concepts:
        parts.append("Concepts: " + ", ".join(ctx.relevant_concepts[:10]))
    if ctx.prior_findings:
        parts.append("Prior findings: " + " | ".join(s[:80] for s in ctx.prior_findings[:5]))
    if ctx.known_constraints:
        parts.append("Constraints: " + "; ".join(ctx.known_constraints[:5]))
    if ctx.related_methods:
        parts.append("Methods: " + ", ".join(ctx.related_methods[:8]))
    text = "\n".join(parts)
    if len(text) > max_tokens * 4:
        text = text[: max_tokens * 4] + "..."
    return text
