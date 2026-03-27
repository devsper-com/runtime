"""Model pricing utilities used for telemetry and budget tracking."""

from __future__ import annotations


PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
    "gemini-1.5-pro": {"input": 3.50, "output": 10.50},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}


def estimate_cost_usd(
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    """Return USD cost from token counts, or None for unknown models."""
    rates = PRICING.get(model)
    if rates is None:
        return None
    pin = max(int(prompt_tokens or 0), 0)
    pout = max(int(completion_tokens or 0), 0)
    return ((pin * rates["input"]) + (pout * rates["output"])) / 1_000_000.0
