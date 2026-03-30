"""Publish devsper events to Redis for platform SSE (devsper:results:{run_id}).

Matches the envelope produced by the FastAPI swarmworker so the web UI and CLI
cloud stream parse events consistently.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RedisEventSink:
    """Stateful DAG enrichment + PUBLISH to devsper:results:{run_id} (same as swarmworker)."""

    def __init__(self, redis_client: Any, channel: str) -> None:
        self.r = redis_client
        self.channel = channel
        self._dag_nodes: dict[str, dict] = {}

    def on_devsper_event(self, event: Any) -> None:
        try:
            payload = event.payload if hasattr(event, "payload") else {}
            event_type = (
                event.type.value if hasattr(event.type, "value") else str(event.type)
            )

            enhanced_payload = dict(payload) if payload else {}

            if "task_id" not in enhanced_payload and "id" in enhanced_payload:
                enhanced_payload["task_id"] = enhanced_payload["id"]
            if "node_id" not in enhanced_payload:
                enhanced_payload["node_id"] = enhanced_payload.get(
                    "task_id"
                ) or enhanced_payload.get("id", "unknown")

            if event_type == "task_created":
                self._dag_nodes[enhanced_payload.get("task_id", "")] = {
                    "id": enhanced_payload.get("task_id", ""),
                    "status": "queued",
                    "description": enhanced_payload.get("description", ""),
                    "agent_type": enhanced_payload.get("role", "worker"),
                    "parent_id": enhanced_payload.get("parent_id"),
                }
                enhanced_payload["metadata"] = self._dag_nodes[
                    enhanced_payload.get("task_id", "")
                ]

            elif event_type == "task_started" or event_type == "agent_started":
                task_id = enhanced_payload.get("task_id", "")
                if task_id in self._dag_nodes:
                    if self._dag_nodes[task_id].get("status") != "waiting_for_input":
                        self._dag_nodes[task_id]["status"] = "running"
                    enhanced_payload["metadata"] = self._dag_nodes[task_id]

            elif event_type == "task_completed":
                task_id = enhanced_payload.get("task_id", "")
                if task_id in self._dag_nodes:
                    self._dag_nodes[task_id]["status"] = "completed"
                    if "output" in enhanced_payload:
                        self._dag_nodes[task_id]["output"] = enhanced_payload["output"]
                    enhanced_payload["metadata"] = self._dag_nodes[task_id]

            elif event_type == "tool_called":
                if "tool" in enhanced_payload:
                    enhanced_payload["tool_name"] = enhanced_payload["tool"]
                if "task_id" in enhanced_payload:
                    task_id = enhanced_payload["task_id"]
                    if task_id in self._dag_nodes:
                        self._dag_nodes[task_id]["tool_name"] = enhanced_payload.get(
                            "tool", ""
                        )
                        enhanced_payload["metadata"] = self._dag_nodes[task_id]

            elif event_type == "clarification_requested":
                task_id = enhanced_payload.get("task_id", "")
                if task_id in self._dag_nodes:
                    self._dag_nodes[task_id]["status"] = "waiting_for_input"
                    hint = enhanced_payload.get("context") or enhanced_payload.get(
                        "question", ""
                    )
                    self._dag_nodes[task_id]["output"] = hint
                    enhanced_payload["metadata"] = self._dag_nodes[task_id]

            if event_type in (
                "task_created",
                "task_started",
                "task_completed",
                "tool_called",
                "clarification_requested",
            ):
                edges = []
                for node_id, node in self._dag_nodes.items():
                    if node.get("parent_id"):
                        edges.append([node["parent_id"], node_id])

                enhanced_payload["dag"] = {
                    "nodes": list(self._dag_nodes.values()),
                    "edges": edges,
                }

            enhanced_event = {
                "type": event_type,
                "timestamp": event.timestamp.isoformat()
                if hasattr(event, "timestamp")
                else datetime.now().isoformat(),
                "payload": enhanced_payload,
            }

            self.r.publish(self.channel, json.dumps(enhanced_event))
        except Exception as e:
            logger.warning("Failed to publish event to %s: %s", self.channel, e)
            try:
                self.r.publish(self.channel, event.model_dump_json())
            except Exception:
                pass


class ChainedDevSperSink:
    """Forward on_devsper_event to multiple sinks (Redis results + platform internal, etc.)."""

    def __init__(self, sinks: list[Any]) -> None:
        self._sinks = [s for s in sinks if s is not None]

    def on_devsper_event(self, event: Any) -> None:
        for s in self._sinks:
            try:
                on = getattr(s, "on_devsper_event", None)
                if callable(on):
                    on(event)
            except Exception:
                logger.debug("chained sink failed", exc_info=True)


def _results_redis_url() -> str:
    import os

    return (
        os.environ.get("DEVSPER_RESULTS_REDIS_URL", "").strip()
        or os.environ.get("REDIS_URL", "").strip()
    )


def build_reporter_sinks_chain(events_folder_path: str) -> Optional[Any]:
    """Build Redis results sink and/or platform runtime forwarder from env.

    - Publishes devsper-shaped events to devsper:results:{DEVSPER_PLATFORM_RUN_ID}
      when DEVSPER_PLATFORM_RUN_ID and (DEVSPER_RESULTS_REDIS_URL or REDIS_URL) are set.
    - Adds PlatformRuntimeEventSink when DEVSPER_PLATFORM_RUNTIME_EVENTS is enabled
      (see platform_sink_from_env).
    """
    import os

    from devsper.platform.runtime_events import platform_sink_from_env

    sinks: list[Any] = []
    run_id = (os.environ.get("DEVSPER_PLATFORM_RUN_ID") or "").strip()
    redis_url = _results_redis_url()

    if run_id and redis_url:
        try:
            import redis as redis_mod

            r = redis_mod.Redis.from_url(redis_url, decode_responses=True)
            sinks.append(RedisEventSink(r, f"devsper:results:{run_id}"))
        except Exception as e:
            logger.warning("Could not create Redis results sink: %s", e)

    ps = platform_sink_from_env(events_folder_path)
    if ps is not None:
        sinks.append(ps)

    if not sinks:
        return None
    if len(sinks) == 1:
        return sinks[0]
    return ChainedDevSperSink(sinks)
