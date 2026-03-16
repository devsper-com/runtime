"""
Updated top-k selection: similarity × reliability (blended score).
"""

import os

from devsper.memory.embeddings import embed_text
from devsper.tools.base import Tool

from devsper.tools.scoring.store import ToolScoreStore, ToolScore


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def select_tools_scored(
    task_description: str,
    available_tools: list[Tool],
    top_k: int,
    score_store: ToolScoreStore | None,
) -> list[Tool]:
    """
    Select top_k tools by blended score: 70% similarity + 30% reliability.
    New tools (< 5 calls) get neutral 0.75 reliability. If DEVSPER_DISABLE_TOOL_SCORING=1
    or score_store is None, ranking is similarity-only.
    """
    if not available_tools:
        return []
    if top_k <= 0:
        return available_tools

    disable = os.environ.get("DEVSPER_DISABLE_TOOL_SCORING", "").strip() == "1"
    use_reliability = not disable and score_store is not None

    task_embedding = embed_text(task_description or " ")
    tool_texts = [f"{t.name}: {t.description}" for t in available_tools]
    tool_embeddings = [embed_text(t) for t in tool_texts]

    scored: list[tuple[Tool, float]] = []
    for tool, te in zip(available_tools, tool_embeddings):
        sim = _cosine_similarity(task_embedding, te)
        if use_reliability:
            ts = score_store.get_score(tool.name)
            reliability = (
                ts.composite_score if ts and not ts.is_new else 0.75
            )
            blended = (sim * 0.70) + (reliability * 0.30)
        else:
            blended = sim
        scored.append((tool, blended))

    scored.sort(key=lambda x: -x[1])
    return [t for t, _ in scored[:top_k]]
