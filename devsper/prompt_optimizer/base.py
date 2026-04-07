"""
Abstract base for prompt optimizer backends.

All backends follow the same singleton-factory pattern as memory and LLM providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class OptimizeRequest:
    """Input to the optimizer."""

    base_prompt: str                          # current system/role prompt
    examples: list[tuple[str, str]]           # (task, good_output) training pairs
    metric: Callable | None = None            # (EvalCase, str) -> float, optional
    role: str = "general"                     # agent role being optimized
    model: str = "gpt-4o-mini"               # LLM to use during optimization
    max_demos: int = 4                        # max few-shot examples to include
    n_iterations: int = 10                    # iterations for evolutionary backends
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizeResult:
    """Output from the optimizer."""

    optimized_prompt: str
    backend: str
    score_before: float | None = None
    score_after: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PromptOptimizerBackend(ABC):
    """Abstract async interface for all prompt optimizer backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier: 'noop', 'dspy', 'gepa'."""
        ...

    @abstractmethod
    async def optimize(self, request: OptimizeRequest) -> OptimizeResult:
        """Run optimization; return an optimized prompt string."""
        ...

    @abstractmethod
    async def health(self) -> bool:
        """Return True if the backend is available."""
        ...
