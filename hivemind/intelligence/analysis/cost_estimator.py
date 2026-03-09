"""
Cost estimation from token counts and model pricing.
"""

from hivemind.intelligence.analysis.run_report import TaskSummary


MODEL_PRICING = {
    # (input_per_1k_tokens, output_per_1k_tokens) in USD
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.000150, 0.000600),
    "claude-opus-4": (0.015, 0.075),
    "claude-sonnet-4": (0.003, 0.015),
    "claude-haiku-4": (0.00025, 0.00125),
    "gemini-1.5-pro": (0.00125, 0.005),
    "gemini-1.5-flash": (0.000075, 0.000300),
}


class CostEstimator:
    """Estimate run cost from task token usage and model pricing."""

    @staticmethod
    def estimate(
        tasks: list[TaskSummary],
        models_used: list[str],
    ) -> float | None:
        """
        Compute total USD cost from token counts and model pricing.
        Returns None if token counts are not available (don't guess).
        """
        if not tasks and not models_used:
            return None
        total = 0.0
        any_tokens = False
        for t in tasks:
            if t.tokens_used is None:
                continue
            any_tokens = True
            model = models_used[0] if models_used else None
            if not model:
                return None
            pricing = MODEL_PRICING.get(model)
            if not pricing:
                # Try prefix match for model variants
                for key in MODEL_PRICING:
                    if model.startswith(key) or key in model:
                        pricing = MODEL_PRICING[key]
                        break
                if not pricing:
                    return None
            input_per_1k, output_per_1k = pricing
            # Assume 50/50 split if we only have total; task summary has tokens_used as single int
            inp = t.tokens_used // 2
            out = t.tokens_used - inp
            total += (inp / 1000.0) * input_per_1k + (out / 1000.0) * output_per_1k
        if not any_tokens:
            return None
        return round(total, 4)

    @staticmethod
    def format_cost(usd: float | None) -> str:
        """Return '$0.0023' or 'unknown'."""
        if usd is None:
            return "unknown"
        return f"${usd:.4f}"
