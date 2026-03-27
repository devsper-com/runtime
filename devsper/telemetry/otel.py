"""OpenTelemetry setup and span helpers for devsper runs."""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Iterator

from devsper.telemetry.pricing import estimate_cost_usd

log = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency runtime fallback
    trace = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    ConsoleSpanExporter = None
    OTLPSpanExporter = None
    _OTEL_AVAILABLE = False


_INITIALIZED = False


def _get_service_version() -> str:
    try:
        from devsper import __version__
        return str(__version__)
    except Exception:
        return "unknown"


def init_tracing() -> None:
    """Initialize global tracer provider once."""
    global _INITIALIZED
    if _INITIALIZED or not _OTEL_AVAILABLE:
        _INITIALIZED = True
        return
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    headers: dict[str, str] = {}
    try:
        from devsper.config import get_config

        cfg = get_config()
        tele = getattr(cfg, "telemetry", None)
        if tele is not None:
            if getattr(tele, "otel_enabled", True) is False:
                _INITIALIZED = True
                return
            cfg_endpoint = str(getattr(tele, "otel_endpoint", "") or "").strip()
            if cfg_endpoint and not endpoint:
                endpoint = cfg_endpoint
            hdrs = getattr(tele, "otel_headers", {}) or {}
            if isinstance(hdrs, dict):
                headers = {str(k): str(v) for k, v in hdrs.items()}
    except Exception:
        pass
    resource = Resource.create(
        {
            "service.name": "devsper",
            "service.version": _get_service_version(),
        }
    )
    provider = TracerProvider(resource=resource)
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
    else:
        exporter = ConsoleSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _INITIALIZED = True


def get_tracer():
    """Return devsper tracer. Falls back to no-op tracer if OTEL deps are absent."""
    if _OTEL_AVAILABLE:
        init_tracing()
        return trace.get_tracer("devsper")
    return _NoopTracer()


@contextlib.contextmanager
def instrument_swarm_run(run_id: str, task: str) -> Iterator[object]:
    """Top-level context manager for `swarm.run` span."""
    tracer = get_tracer()
    with tracer.start_as_current_span("swarm.run") as span:
        if span is not None:
            _set_attr(span, "devsper.run.id", run_id)
            _set_attr(span, "run_id", run_id)
            _set_attr(span, "task_preview", (task or "")[:200])
        yield span


def annotate_span(
    span: object,
    *,
    run_id: str | None = None,
    task_id: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> float | None:
    """Add standard devsper telemetry fields and return computed cost (if known)."""
    if span is None:
        return None
    if run_id:
        _set_attr(span, "devsper.run.id", run_id)
    if task_id:
        _set_attr(span, "devsper.task.id", task_id)
    if model:
        _set_attr(span, "model", model)
    if prompt_tokens is not None:
        _set_attr(span, "prompt_tokens", int(prompt_tokens))
    if completion_tokens is not None:
        _set_attr(span, "completion_tokens", int(completion_tokens))
    if model:
        cost = estimate_cost_usd(model, prompt_tokens, completion_tokens)
        if cost is not None:
            _set_attr(span, "devsper.cost.usd", float(cost))
        return cost
    return None


def record_exception(span: object, exc: Exception) -> None:
    """Attach failure attributes to span and record exception."""
    if span is None:
        return
    _set_attr(span, "error.type", type(exc).__name__)
    _set_attr(span, "exception.message", str(exc))
    try:
        span.record_exception(exc)  # type: ignore[attr-defined]
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))  # type: ignore[union-attr]
    except Exception:
        pass


def _set_attr(span: object, key: str, value: object) -> None:
    try:
        span.set_attribute(key, value)  # type: ignore[attr-defined]
    except Exception:
        pass


class _NoopSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def set_attribute(self, key: str, value: object) -> None:
        return None

    def record_exception(self, exc: Exception) -> None:
        return None

    def set_status(self, status: object) -> None:
        return None


class _NoopTracer:
    def start_as_current_span(self, name: str):
        return _NoopSpan()
