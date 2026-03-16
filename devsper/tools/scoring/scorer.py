"""
ToolScorer: compute composite score from raw stats.
"""


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def compute_composite_score(stats: dict) -> float:
    """
    Compute composite reliability score from stats dict with keys:
    success_rate, avg_latency_ms, total_calls, recent_failures.
    Returns 0.05--1.0.
    """
    total_calls = stats.get("total_calls", 0)
    if total_calls < 5:
        return 0.75
    success_rate = stats.get("success_rate", 0.0)
    if success_rate == 0.0 and total_calls >= 10:
        return 0.05
    avg_latency_ms = stats.get("avg_latency_ms", 0.0)
    recent_failures = stats.get("recent_failures", 0)
    reliability = success_rate
    speed = 1.0 - _clamp(avg_latency_ms / 10000.0, 0.0, 1.0)
    recency = 1.0 - (recent_failures / 20.0)
    composite = (reliability * 0.50) + (speed * 0.30) + (recency * 0.20)
    return _clamp(composite, 0.05, 1.0)


def score_label(score: float) -> str:
    """Return label for a composite score."""
    if score >= 0.85:
        return "excellent"
    if score >= 0.65:
        return "good"
    if score >= 0.40:
        return "degraded"
    return "poor"
