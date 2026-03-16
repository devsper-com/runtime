"""
v1.6: Route tasks to simple/medium/complex tiers and select model (fast / worker / quality).
"""

from typing import Any, Literal

from devsper.types.task import Task


TIERS: dict[str, dict[str, Any]] = {
    "simple": {
        "max_tools": 2,
        "max_tokens_est": 500,
        "roles": ["summarize", "extract", "format"],
    },
    "medium": {
        "max_tools": 5,
        "max_tokens_est": 2000,
        "roles": ["research", "analysis", "code"],
    },
    "complex": {
        "max_tools": 99,
        "max_tokens_est": 99999,
        "roles": ["architect", "critic", "experiment"],
    },
}


class TaskComplexityRouter:
    """Classify task complexity and select model tier (simple → fast, medium → worker, complex → quality)."""

    TIERS = TIERS

    def classify(self, task: Task, tools_selected: list[Any]) -> Literal["simple", "medium", "complex"]:
        """
        Score task complexity:
        - Role → base tier (simple/medium/complex from TIERS)
        - Tool count → upgrade tier if tools_selected > threshold
        - Description length → upgrade if > 200 words
        - Dependencies count → upgrade if task.dependencies > 3
        - Speculative flag → downgrade one tier
        Return final tier.
        """
        base = "medium"
        role = (getattr(task, "role", None) or "").lower()
        for tier, cfg in TIERS.items():
            if role in [r.lower() for r in cfg["roles"]]:
                base = tier
                break

        tier = base
        n_tools = len(tools_selected) if tools_selected else 0
        if n_tools > TIERS["simple"]["max_tools"] and tier == "simple":
            tier = "medium"
        if n_tools > TIERS["medium"]["max_tools"] and tier == "medium":
            tier = "complex"

        words = len((task.description or "").split())
        if words > 200 and tier == "simple":
            tier = "medium"
        if words > 200 and tier == "medium":
            tier = "complex"

        deps = len(task.dependencies) if task.dependencies else 0
        if deps > 3 and tier == "simple":
            tier = "medium"
        if deps > 3 and tier == "medium":
            tier = "complex"

        if getattr(task, "speculative", False):
            if tier == "complex":
                tier = "medium"
            elif tier == "medium":
                tier = "simple"

        return tier

    def select_model(self, tier: str, config: Any) -> str:
        """
        simple  → config.fast_model (or config.fast) — default: worker if not set
        medium  → config.worker_model (or config.worker)
        complex → config.quality_model (or config.quality) — default: planner
        If model not configured: fall back to config.worker for all tiers.
        """
        worker = getattr(config, "worker", None) or getattr(config, "worker_model", "mock")
        planner = getattr(config, "planner", None) or getattr(config, "planner_model", "mock")
        fast = getattr(config, "fast", None)
        quality = getattr(config, "quality", None) or planner

        if tier == "simple":
            return fast if fast else worker
        if tier == "complex":
            return quality
        return worker
