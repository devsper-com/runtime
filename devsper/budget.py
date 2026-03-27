"""Budget tracking utilities for swarm runs."""

from __future__ import annotations

import contextlib
import threading
from collections import defaultdict
from dataclasses import dataclass, field

from devsper.telemetry.pricing import estimate_cost_usd


class BudgetExceededError(RuntimeError):
    def __init__(self, spent: float, limit: float):
        super().__init__(f"Budget exceeded: spent=${spent:.6f} limit=${limit:.6f}")
        self.spent = float(spent)
        self.limit = float(limit)


@dataclass
class BudgetManager:
    """Thread-safe budget tracker for one run."""

    limit_usd: float = 0.0
    on_exceeded: str = "warn"  # warn | stop | raise
    alert_at_pct: int = 80
    _spent_usd: float = 0.0
    _breakdown: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _exceeded: bool = False
    _stop_event: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _tasks_skipped: int = 0

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return float(self._spent_usd)

    @property
    def remaining_usd(self) -> float:
        if self.limit_usd <= 0:
            return float("inf")
        with self._lock:
            return max(0.0, self.limit_usd - self._spent_usd)

    @property
    def exceeded(self) -> bool:
        with self._lock:
            return bool(self._exceeded)

    @property
    def breakdown(self) -> dict[str, float]:
        with self._lock:
            return {k: float(v) for k, v in self._breakdown.items()}

    @property
    def tasks_skipped(self) -> int:
        with self._lock:
            return int(self._tasks_skipped)

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def add_skipped(self, n: int = 1) -> None:
        with self._lock:
            self._tasks_skipped += max(0, int(n))

    def consume(
        self,
        *,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> float | None:
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
        if cost is None:
            return None
        with self._lock:
            self._spent_usd += cost
            self._breakdown[model] += cost
            if self.limit_usd > 0 and self._spent_usd >= self.limit_usd:
                self._exceeded = True
                if self.on_exceeded == "stop":
                    self._stop_event.set()
                elif self.on_exceeded == "raise":
                    raise BudgetExceededError(self._spent_usd, self.limit_usd)
        return cost

    @contextlib.contextmanager
    def track(
        self,
        *,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ):
        self.consume(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        yield
