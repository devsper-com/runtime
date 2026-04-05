"""
Forward swarm EventLog entries to the platform internal runtime events API (non-blocking).

Uses a bounded queue + background thread so execution never waits on HTTP.
Optional: XADD to devsper:runtime_events when DEVSPER_PLATFORM_RUNTIME_EVENTS_REDIS_URL is set.

Environment:
- DEVSPER_PLATFORM_RUNTIME_EVENTS: 1/true/on to enable (default off).
- DEVSPER_PLATFORM_API_URL: base URL (e.g. http://localhost:8080).
- DEVSPER_PLATFORM_INTERNAL_SECRET: Bearer token for POST /internal/v1/runtime/events.
- DEVSPER_PLATFORM_RUN_ID, DEVSPER_PLATFORM_TRACE_ID: correlate with a platform run (UUIDs).
- DEVSPER_PLATFORM_RUNTIME_EVENTS_REDIS_URL: if set, publish via Redis stream instead of HTTP.
- DEVSPER_PLATFORM_RUNTIME_EVENTS_PROGRESS_INTERVAL_MS: min gap between run_progress events (default 400).
- DEVSPER_DEBUG_EVENTS=1: log forwarded event types and platform payloads (see devsper.debug_events).
- tool_called events are forwarded without that throttle and use event_type tool_called for Postgres/SSE.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Optional

from devsper.contracts.platform_event_type import PlatformEventType
from devsper.debug_events import log_platform_body, log_runtime_emit
from devsper.types.event import Event, events

_LOG = logging.getLogger(__name__)

_RUN_STARTED = frozenset(
    {
        events.SWARM_STARTED,
        events.EXECUTOR_STARTED,
    }
)
_TASK_STEP_STARTED = frozenset({events.TASK_STARTED})
_TASK_STEP_COMPLETED = frozenset({events.TASK_COMPLETED})
_RUN_COMPLETED = frozenset({events.RUN_COMPLETED})
_RUN_FAILED = frozenset({events.TASK_FAILED, events.RUN_FAILED})
_RUN_PROGRESS = frozenset(
    {
        events.PLANNER_STARTED,
        events.PLANNER_FINISHED,
        events.REASONING_NODE_ADDED,
        events.BUDGET_WARNING,
        events.TASK_CREATED,
        events.TASK_MODEL_SELECTED,
        events.AGENT_BROADCAST,
        events.RUN_MANIFEST_EMITTED,
    }
)
_TOOL_EVENTS = frozenset({events.TOOL_CALLED})
_CLARIFICATION_REQUESTED = frozenset({events.CLARIFICATION_REQUESTED, events.CLARIFICATION_NEEDED})
_CLARIFICATION_ANSWERED = frozenset({events.CLARIFICATION_RECEIVED})


def _timestamp_ms(ev: Event) -> int:
    ts = ev.timestamp
    if hasattr(ts, "timestamp"):
        return int(ts.timestamp() * 1000)
    return int(time.time() * 1000)


def map_devsper_event_to_platform(ev: Event) -> Optional[str]:
    """Map in-process devsper.events enum to platform ingest `event_type` string."""
    et = ev.type
    if et == events.WORKER_ASSIGNED:
        return PlatformEventType.WORKER_ASSIGNED
    if et == events.SPECULATIVE_STARTED:
        return PlatformEventType.SPECULATIVE_TASK_STARTED
    if et == events.SPECULATIVE_CANCELLED:
        return PlatformEventType.SPECULATIVE_TASK_CANCELLED
    if et == events.HITL_REQUESTED:
        return PlatformEventType.HITL_REQUESTED
    if et == events.HITL_RESOLVED:
        return PlatformEventType.HITL_RESOLVED
    if et == events.EXECUTOR_FINISHED:
        return PlatformEventType.EXECUTOR_FINISHED
    if et == events.AGENT_STARTED:
        return PlatformEventType.AGENT_STARTED
    if et == events.AGENT_FINISHED:
        return PlatformEventType.AGENT_FINISHED
    if et in _RUN_STARTED:
        return PlatformEventType.RUN_STARTED
    if et in _TASK_STEP_STARTED:
        return PlatformEventType.STEP_STARTED
    if et in _TASK_STEP_COMPLETED:
        return PlatformEventType.STEP_COMPLETED
    if et in _RUN_COMPLETED:
        return PlatformEventType.RUN_COMPLETED
    if et in _RUN_FAILED:
        return PlatformEventType.RUN_FAILED
    if et in _TOOL_EVENTS:
        return PlatformEventType.TOOL_CALLED
    if et in _CLARIFICATION_REQUESTED:
        return PlatformEventType.CLARIFICATION_REQUESTED
    if et in _CLARIFICATION_ANSWERED:
        return PlatformEventType.CLARIFICATION_ANSWERED
    if et in _RUN_PROGRESS:
        return PlatformEventType.RUN_PROGRESS
    return None


@dataclass
class PlatformRuntimeSinkConfig:
    api_base_url: str
    internal_secret: str
    platform_run_id: str
    platform_trace_id: str = ""
    redis_url: str = ""
    progress_interval_ms: int = 400
    queue_maxsize: int = 512
    http_timeout_s: float = 8.0


class PlatformRuntimeEventSink:
    """Thread-safe non-blocking forwarder to platform (HTTP or Redis stream)."""

    def __init__(self, cfg: PlatformRuntimeSinkConfig, wal_path: str) -> None:
        self._cfg = cfg
        self._wal_path = wal_path
        self._q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=cfg.queue_maxsize)
        self._stop = threading.Event()
        self._last_progress_mono: dict[str, float] = {}
        self._thread = threading.Thread(target=self._loop, name="platform-runtime-events", daemon=True)
        self._seq_by_run: dict[str, int] = {}
        self._log = logging.getLogger(__name__)
        self._thread.start()

    def close(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout=timeout_s)

    def on_devsper_event(self, ev: Event) -> None:
        raw_type = ev.type.value if hasattr(ev.type, "value") else str(ev.type)
        mapped = map_devsper_event_to_platform(ev)
        log_runtime_emit(
            "forwarder_map",
            {"devsper_type": raw_type, "platform_event_type": mapped, "payload_keys": list((ev.payload or {}).keys())},
        )
        ptype = mapped
        if ptype is None:
            return
        rid = (self._cfg.platform_run_id or "").strip()
        if not rid:
            return
        if ptype == PlatformEventType.RUN_PROGRESS:
            key = rid
            now = time.monotonic()
            min_gap = max(0.05, self._cfg.progress_interval_ms / 1000.0)
            last = self._last_progress_mono.get(key, 0.0)
            if now - last < min_gap:
                return
            self._last_progress_mono[key] = now

        body: dict[str, Any] = {
            "run_id": rid,
            "trace_id": (self._cfg.platform_trace_id or "").strip(),
            "event_type": ptype,
            "timestamp": _timestamp_ms(ev),
            "payload": dict(ev.payload or {}),
        }
        body["event_id"] = self._event_id_for(ev, body)
        body["sequence_id"] = self._next_sequence_id(rid)
        body["payload"]["event_id"] = body["event_id"]
        body["payload"]["sequence_id"] = body["sequence_id"]
        log_platform_body(body)
        try:
            self._q.put_nowait(body)
        except queue.Full:
            self._wal_append(body)
        self._log.debug(
            "runtime event queued run_id=%s event_id=%s sequence_id=%s event_type=%s",
            rid,
            body["event_id"],
            body["sequence_id"],
            ptype,
        )

    def _next_sequence_id(self, run_id: str) -> int:
        cur = int(self._seq_by_run.get(run_id, 0))
        nxt = cur + 1
        self._seq_by_run[run_id] = nxt
        return nxt

    def _event_id_for(self, ev: Event, body: dict[str, Any]) -> str:
        if getattr(ev, "event_id", ""):
            return str(ev.event_id)
        payload = dict(body.get("payload") or {})
        identity = (
            str(payload.get("request_id") or "").strip()
            or str(payload.get("task_id") or "").strip()
            or str(payload.get("node_id") or "").strip()
        )
        if identity:
            seed = f'{body.get("run_id","")}:{body.get("event_type","")}:{identity}:{json.dumps(payload, sort_keys=True, default=str)}'
            return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]
        import uuid

        return uuid.uuid4().hex

    def _wal_append(self, body: dict[str, Any]) -> None:
        try:
            with open(self._wal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(body, default=str) + "\n")
        except OSError:
            pass

    def _loop(self) -> None:
        redis_client = None
        if (self._cfg.redis_url or "").strip():
            try:
                import redis

                redis_client = redis.Redis.from_url(self._cfg.redis_url, decode_responses=True)
            except Exception:
                redis_client = None

        import httpx

        url = (self._cfg.api_base_url or "").rstrip("/") + "/internal/v1/runtime/events"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._cfg.internal_secret}",
        }

        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.4)
            except queue.Empty:
                continue
            ok = False
            backoff_s = 0.2
            for _ in range(3):
                ok = self._deliver_one(item, redis_client, httpx, url, headers)
                if ok:
                    break
                time.sleep(backoff_s)
                backoff_s = min(backoff_s * 2.0, 1.5)
            if not ok:
                self._wal_append(item)

    def _deliver_one(
        self,
        item: dict[str, Any],
        redis_client: Any,
        httpx_mod: Any,
        url: str,
        headers: dict[str, str],
    ) -> bool:
        if redis_client is not None:
            try:
                raw = json.dumps(item, default=str)
                redis_client.xadd("devsper:runtime_events", {"payload": raw})
                return True
            except Exception:
                pass
        try:
            with httpx_mod.Client(timeout=self._cfg.http_timeout_s) as client:
                r = client.post(url, headers=headers, json=item)
                return r.status_code < 300
        except Exception:
            return False


def platform_sink_from_env(
    events_folder_path: str, run_id_override: str | None = None
) -> Optional[PlatformRuntimeEventSink]:
    """Build sink from env if enabled; returns None if disabled or misconfigured.

    run_id_override: when set (e.g. swarmworker request body), used instead of
    DEVSPER_PLATFORM_RUN_ID so forwarded events match the hosted run.
    """
    en = os.environ.get("DEVSPER_PLATFORM_RUNTIME_EVENTS", "").strip().lower()
    if en not in ("1", "true", "on", "yes"):
        return None
    api = (os.environ.get("DEVSPER_PLATFORM_API_URL") or "").strip().rstrip("/")
    secret = (os.environ.get("DEVSPER_PLATFORM_INTERNAL_SECRET") or "").strip()
    run_id = (run_id_override or os.environ.get("DEVSPER_PLATFORM_RUN_ID") or "").strip()
    if not api or not secret or not run_id:
        return None
    trace_id = (os.environ.get("DEVSPER_PLATFORM_TRACE_ID") or "").strip()
    redis_url = (os.environ.get("DEVSPER_PLATFORM_RUNTIME_EVENTS_REDIS_URL") or "").strip()
    interval_ms = 400
    raw_iv = os.environ.get("DEVSPER_PLATFORM_RUNTIME_EVENTS_PROGRESS_INTERVAL_MS", "").strip()
    if raw_iv.isdigit():
        interval_ms = max(50, int(raw_iv))
    os.makedirs(events_folder_path, exist_ok=True)
    wal_path = os.path.join(events_folder_path, "platform_runtime_events.wal")
    cfg = PlatformRuntimeSinkConfig(
        api_base_url=api,
        internal_secret=secret,
        platform_run_id=run_id,
        platform_trace_id=trace_id,
        redis_url=redis_url,
        progress_interval_ms=interval_ms,
    )
    return PlatformRuntimeEventSink(cfg, wal_path=wal_path)
