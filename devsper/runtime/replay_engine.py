"""
Deterministic replay: reconstruct entire swarm execution from an event log.

Includes: planner decisions, scheduler events, agent prompts (when logged),
tool calls, reasoning graph updates.
"""

import os
from pathlib import Path
from devsper.types.event import Event


def _find_log_path(events_dir: str | Path, run_id: str) -> str | None:
    """Find events JSONL file for run_id (stem of filename). Returns path or None."""
    path = Path(events_dir)
    if not path.is_dir():
        return None
    candidate = path / f"{run_id}.jsonl"
    if candidate.is_file():
        return str(candidate)
    for f in path.glob("*.jsonl"):
        if f.stem == run_id:
            return str(f)
    return None


def _load_events(log_path: str) -> list[Event]:
    """Load events from a JSONL file."""
    if not os.path.isfile(log_path):
        return []
    out = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Event.model_validate_json(line))
            except Exception:
                continue
    return out


def replay_run(
    run_id: str,
    events_dir: str | Path | None = None,
) -> str:
    """
    Reconstruct the entire swarm execution for run_id.
    Returns a transcript string: planner decisions, scheduler (task) events,
    executor/agent lifecycle, tool calls, reasoning graph updates.
    """
    if events_dir is None:
        try:
            from devsper.config import get_config

            events_dir = get_config().events_dir
        except Exception:
            events_dir = ".devsper/events"

    log_path = _find_log_path(events_dir, run_id)
    if not log_path:
        return f"No event log found for run_id: {run_id} (looked in {events_dir})"

    evs = _load_events(log_path)
    if not evs:
        return f"Empty event log for run_id: {run_id}"

    evs.sort(key=lambda e: e.timestamp)
    lines = [f"# Replay: {run_id}", ""]

    for e in evs:
        event_type = e.type.value if hasattr(e.type, "value") else str(e.type)
        payload = e.payload or {}
        ts = getattr(e.timestamp, "isoformat", lambda: str(e.timestamp))()

        if event_type == "swarm_started":
            lines.append(f"[{ts}] SWARM_STARTED")
            lines.append(f"  user_task: {payload.get('user_task', '')[:200]}")
        elif event_type == "planner_started":
            lines.append(
                f"[{ts}] PLANNER_STARTED  task_id={payload.get('task_id', '')}"
            )
        elif event_type == "task_created":
            lines.append(f"[{ts}] TASK_CREATED  task_id={payload.get('task_id', '')}")
            lines.append(f"  description: {(payload.get('description') or '')[:120]}")
        elif event_type == "planner_finished":
            lines.append(
                f"[{ts}] PLANNER_FINISHED  subtask_count={payload.get('subtask_count', 0)}"
            )
        elif event_type == "executor_started":
            lines.append(f"[{ts}] EXECUTOR_STARTED")
        elif event_type == "agent_started":
            lines.append(f"[{ts}] AGENT_STARTED  task_id={payload.get('task_id', '')}")
        elif event_type == "task_started":
            lines.append(f"[{ts}] TASK_STARTED  task_id={payload.get('task_id', '')}")
        elif event_type == "tool_called":
            lines.append(
                f"[{ts}] TOOL_CALLED  task_id={payload.get('task_id', '')}  tool={payload.get('tool', '')}"
            )
            lines.append(
                f"  result_preview: {(payload.get('result_preview') or '')[:150]}"
            )
        elif event_type == "reasoning_node_added":
            lines.append(
                f"[{ts}] REASONING_NODE_ADDED  node_id={payload.get('node_id', '')}  task_id={payload.get('task_id', '')}"
            )
        elif event_type == "task_completed":
            lines.append(f"[{ts}] TASK_COMPLETED  task_id={payload.get('task_id', '')}")
        elif event_type == "task_failed":
            lines.append(
                f"[{ts}] TASK_FAILED  task_id={payload.get('task_id', '')}  error={payload.get('error', '')[:100]}"
            )
        elif event_type == "agent_finished":
            lines.append(f"[{ts}] AGENT_FINISHED  task_id={payload.get('task_id', '')}")
        elif event_type == "executor_finished":
            lines.append(f"[{ts}] EXECUTOR_FINISHED")
        elif event_type == "swarm_finished":
            lines.append(
                f"[{ts}] SWARM_FINISHED  task_count={payload.get('task_count', 0)}"
            )
        else:
            lines.append(f"[{ts}] {event_type.upper()}  {payload}")
        lines.append("")

    return "\n".join(lines).rstrip()


def list_run_ids(events_dir: str | Path | None = None) -> list[str]:
    """List run IDs that have event logs (from *.jsonl in events_dir)."""
    if events_dir is None:
        try:
            from devsper.config import get_config

            events_dir = get_config().events_dir
        except Exception:
            events_dir = ".devsper/events"
    path = Path(events_dir)
    if not path.is_dir():
        return []
    ids_ = [f.stem for f in path.glob("*.jsonl")]
    return sorted(ids_, reverse=True)
