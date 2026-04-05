"""
Per-request execution context for platform swarmworker (thread-local).
Used for org-scoped tool metrics in Redis.
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

_tls = threading.local()


def set_execution_org(org_id: str) -> None:
    _tls.org_id = (org_id or "").strip()


def clear_execution_org() -> None:
    _tls.org_id = ""


def get_execution_org_id() -> str:
    return getattr(_tls, "org_id", "") or ""


def record_tool_call(tool_name: str, ok: bool, latency_ms: int) -> None:
    """Best-effort Redis counters: devsper:tool_metrics:{org_id} hash fields {tool}:calls, :fail, :lat_ms."""
    oid = get_execution_org_id()
    if not oid or not tool_name:
        return
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return
    try:
        import redis  # type: ignore[import-untyped]
    except ImportError:
        return
    key = f"devsper:tool_metrics:{oid}"
    prefix = f"{tool_name}:"
    try:
        r = redis.Redis.from_url(url, decode_responses=True)
        p = r.pipeline()
        p.hincrby(key, prefix + "calls", 1)
        if not ok:
            p.hincrby(key, prefix + "fail", 1)
        p.hincrby(key, prefix + "lat_ms", max(0, int(latency_ms)))
        p.expire(key, 86400 * 30)  # 30d retention
        p.execute()
    except Exception as ex:
        logger.debug("tool metrics redis skipped: %s", ex)
