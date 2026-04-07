"""
Core types for the devsper eval harness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


# A metric function: (case, actual_output) -> float in [0, 1]
MetricFn = Callable[["EvalCase", str], float]


@dataclass
class EvalCase:
    """A single evaluation example."""

    id: str
    task: str                          # prompt / task description
    expected: str                      # expected output (or pattern)
    role: str = "general"              # agent role to evaluate
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task": self.task,
            "expected": self.expected,
            "role": self.role,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvalCase":
        return cls(
            id=d["id"],
            task=d["task"],
            expected=d.get("expected", ""),
            role=d.get("role", "general"),
            metadata=d.get("metadata", {}),
        )


@dataclass
class EvalResult:
    """Result of running a single EvalCase."""

    case: EvalCase
    actual: str
    score: float                       # 0.0–1.0
    passed: bool                       # score >= threshold
    duration_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "case_id": self.case.id,
            "task": self.case.task,
            "expected": self.case.expected,
            "actual": self.actual,
            "score": self.score,
            "passed": self.passed,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


@dataclass
class EvalSummary:
    """Aggregate results for an eval run."""

    results: list[EvalResult]
    metric_name: str
    role: str
    pass_threshold: float = 0.5
    optimizer_backend: str = "noop"

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def mean_score(self) -> float:
        scores = [r.score for r in self.results]
        return sum(scores) / len(scores) if scores else 0.0

    def as_examples(self) -> list[tuple[str, str]]:
        """Return (task, actual) pairs for passed cases — training data for optimizer."""
        return [(r.case.task, r.actual) for r in self.results if r.passed]

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "pass_rate": round(self.pass_rate, 4),
            "mean_score": round(self.mean_score, 4),
            "metric": self.metric_name,
            "role": self.role,
            "optimizer_backend": self.optimizer_backend,
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
