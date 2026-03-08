"""
Replay swarm execution from an event log.

Load events.jsonl, group by task, reconstruct execution timeline, print step-by-step replay.
"""

import os
from hivemind.types.event import Event


def _load_events(log_path: str) -> list[Event]:
    """Load events from a JSONL file."""
    if not os.path.exists(log_path):
        return []
    events_list = []
    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events_list.append(Event.model_validate_json(line))
            except Exception:
                continue
    return events_list


def replay_execution(log_path: str) -> str:
    """
    Replay swarm execution from the event log at log_path.

    Loads events.jsonl, sorts by timestamp, and returns a step-by-step replay transcript
    (e.g. [planner_started] task_1 created agent_started task_1 ...).
    """
    events_list = _load_events(log_path)
    if not events_list:
        return f"No events found at {log_path}"

    events_list.sort(key=lambda e: e.timestamp)

    lines = []
    for e in events_list:
        event_type = e.type.value if hasattr(e.type, "value") else str(e.type)
        payload = e.payload or {}
        task_id = payload.get("task_id", "")
        part = f"[{event_type}]"
        if task_id:
            part += f" {task_id}"
        if event_type == "task_created" and payload.get("description"):
            part += f" created"
        lines.append(part)

    return "\n".join(lines)
