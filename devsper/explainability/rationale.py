"""Rationale generation (LLM or template) for decision records."""

from devsper.explainability.decision_tree import DecisionRecord


class RationaleGenerator:
    """Generate NL explanation for a DecisionRecord. Cached per task."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    async def generate(self, record: DecisionRecord, model: str = "mock") -> str:
        """Use LLM to generate one-paragraph explanation. Cached per task_id."""
        if record.task_id in self._cache:
            return self._cache[record.task_id]
        try:
            from devsper.utils.models import generate
            prompt = (
                f"Explain in one short paragraph why this AI task was executed this way.\n"
                f"Task: {record.task_description}\n"
                f"Strategy: {record.strategy_selected}. Model: {record.model_selected}. "
                f"Tools used: {', '.join(record.tools_selected)}. Confidence: {record.confidence:.0%}.\n"
                f"Write 2-3 sentences only."
            )
            out = generate(model, prompt)
            self._cache[record.task_id] = out or ""
            return out or self.template_rationale(record)
        except Exception:
            return self.template_rationale(record)

    def template_rationale(self, record: DecisionRecord) -> str:
        """Template-based fallback (no LLM)."""
        return (
            f"Task classified as {record.strategy_selected}. "
            f"Selected {len(record.tools_selected)} tools ({', '.join(record.tools_selected) or 'none'}). "
            f"Used {record.model_selected} ({record.model_tier} tier). "
            f"Confidence: {record.confidence:.0%}."
        )
