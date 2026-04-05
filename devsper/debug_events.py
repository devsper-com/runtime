"""DEVSPER_DEBUG_EVENTS=1 — log runtime → platform → delivery trail (stderr / logging)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_LOG = logging.getLogger("devsper.debug_events")


def debug_events_enabled() -> bool:
    return os.environ.get("DEVSPER_DEBUG_EVENTS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def log_runtime_emit(stage: str, payload: dict[str, Any]) -> None:
    if not debug_events_enabled():
        return
    try:
        line = json.dumps({"debug_events": stage, **payload}, default=str)
    except TypeError:
        line = str(payload)
    _LOG.info(line)


def log_platform_body(body: dict[str, Any]) -> None:
    if not debug_events_enabled():
        return
    try:
        _LOG.info("[platform_event] %s", json.dumps(body, default=str))
    except TypeError:
        _LOG.info("[platform_event] %s", body)
