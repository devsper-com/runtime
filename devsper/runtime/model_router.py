from __future__ import annotations

from dataclasses import dataclass

from devsper.types.task import Task


@dataclass(frozen=True)
class ModelRoute:
    primary: str
    fallbacks: tuple[str, ...] = ()


class ModelRouter:
    """Task/agent model routing with fallback chains."""

    def __init__(
        self,
        planning_model: str = "mock",
        reasoning_model: str = "mock",
        validation_model: str = "mock",
        fallback_models: tuple[str, ...] = (),
    ) -> None:
        self._planning = planning_model
        self._reasoning = reasoning_model
        self._validation = validation_model
        self._fallbacks = tuple(m for m in fallback_models if m)

    def route(self, task: Task) -> ModelRoute:
        desc = (task.description or "").lower()
        role = (getattr(task, "role", None) or "").lower()

        if role in {"planning", "planner"} or "plan" in desc:
            return ModelRoute(primary=self._planning, fallbacks=self._fallbacks)
        if role in {"validation", "critic", "review"} or any(
            token in desc for token in ("validate", "verify", "lint", "test", "check")
        ):
            return ModelRoute(primary=self._validation, fallbacks=self._fallbacks)
        return ModelRoute(primary=self._reasoning, fallbacks=self._fallbacks)

    def route_agent(self, agent: object) -> ModelRoute:
        model = getattr(agent, "model_name", None) or self._reasoning
        return ModelRoute(primary=str(model), fallbacks=self._fallbacks)

