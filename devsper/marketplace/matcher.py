"""
Capability matcher: cosine similarity matching of task description to agent vectors.
"""
from __future__ import annotations

from devsper.marketplace.registry import CapabilityRegistry, AgentCapability
from devsper.marketplace.vectors import embed, cosine_similarity


def match(
    task_description: str,
    registry: CapabilityRegistry,
    top_k: int = 5,
    min_similarity: float = 0.0,
) -> list[tuple[AgentCapability, float]]:
    """
    Find the top-k agents most similar to task_description.
    Returns list of (AgentCapability, similarity_score) sorted descending.
    """
    task_vec = embed(task_description)
    agents = registry.all_agents()
    scored: list[tuple[AgentCapability, float]] = []
    for cap in agents:
        if not cap.vector:
            continue
        sim = cosine_similarity(task_vec, cap.vector)
        if sim >= min_similarity:
            scored.append((cap, sim))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
