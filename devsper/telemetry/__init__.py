"""Telemetry exports."""

from devsper.telemetry.otel import (
    annotate_span,
    get_tracer,
    instrument_swarm_run,
    record_exception,
)
from devsper.telemetry.pricing import PRICING, estimate_cost_usd

__all__ = [
    "PRICING",
    "annotate_span",
    "estimate_cost_usd",
    "get_tracer",
    "instrument_swarm_run",
    "record_exception",
]


def __getattr__(name: str):
    if name == "BudgetManager":
        from devsper.budget import BudgetManager

        return BudgetManager
    raise AttributeError(name)
