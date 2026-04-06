"""Telemetry exports."""

from devsper.telemetry.otel import (
    annotate_span,
    get_tracer,
    instrument_swarm_run,
    record_exception,
)
from devsper.telemetry.pricing import PRICING, estimate_cost_usd
from devsper.telemetry.trulens import (
    get_session as get_trulens_session,
    init_trulens,
    make_recorder as make_trulens_recorder,
)

__all__ = [
    "PRICING",
    "annotate_span",
    "estimate_cost_usd",
    "get_tracer",
    "get_trulens_session",
    "init_trulens",
    "instrument_swarm_run",
    "make_trulens_recorder",
    "record_exception",
]


def __getattr__(name: str):
    if name == "BudgetManager":
        from devsper.budget import BudgetManager

        return BudgetManager
    raise AttributeError(name)
