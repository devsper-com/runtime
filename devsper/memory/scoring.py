"""
Memory scoring: relevance, recency, importance for ranking results.
"""

from datetime import datetime, timezone
from math import exp

from devsper.memory.memory_types import MemoryRecord


def recency_score(record: MemoryRecord, now: datetime | None = None) -> float:
    """Score by recency: newer = higher. Exponential decay."""
    now = now or datetime.now(timezone.utc)
    ts = record.timestamp
    delta = (now - ts).total_seconds()
    # Half-life ~ 1 day: score = 0.5 at 86400 seconds
    half_life = 86400.0
    return exp(-delta * (0.693 / half_life))


def importance_score(record: MemoryRecord) -> float:
    """Heuristic importance: longer content and more tags = slightly higher."""
    base = 1.0
    content_len = len(record.content or "")
    if content_len > 500:
        base += 0.2
    if content_len > 2000:
        base += 0.2
    tag_count = len(record.tags or [])
    if tag_count > 3:
        base += 0.1
    return min(base, 2.0)


def combine_scores(
    similarity: float,
    recency: float,
    importance: float,
    similarity_weight: float = 0.7,
    recency_weight: float = 0.2,
    importance_weight: float = 0.1,
) -> float:
    """Combine normalized scores. Default: similarity dominates."""
    return (
        similarity_weight * similarity
        + recency_weight * recency
        + importance_weight * importance
    )


def score_and_sort(
    records: list[MemoryRecord],
    similarity_scores: list[float] | None = None,
    now: datetime | None = None,
) -> list[tuple[MemoryRecord, float]]:
    """
    Return (record, combined_score) sorted by score descending.
    If similarity_scores is None, use 1.0 for all (recency + importance only).
    """
    if similarity_scores is None:
        similarity_scores = [1.0] * len(records)
    if len(similarity_scores) != len(records):
        similarity_scores = [1.0] * len(records)
    now = now or datetime.now(timezone.utc)
    scored = [
        (
            r,
            combine_scores(
                similarity_scores[i],
                recency_score(r, now),
                importance_score(r),
            ),
        )
        for i, r in enumerate(records)
    ]
    scored.sort(key=lambda x: -x[1])
    return scored
