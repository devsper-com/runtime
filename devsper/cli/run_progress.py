"""
CLI run progress: read event log and return status line + parallel task info for live feedback.
"""

import os


def read_run_status(
    log_path: str | None,
    worker_count: int = 0,
) -> tuple[str, list[str]]:
    """
    Read event log and return (status_message, running_task_ids).
    running_task_ids are task ids that have task_started but not yet task_completed.
    worker_count: if > 0, show "up to N in parallel" in executor messages.
    """
    if not log_path or not os.path.isfile(log_path):
        return "Starting…", []

    events = []
    try:
        from devsper.types.event import Event

        with open(log_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(Event.model_validate_json(line))
                except Exception:
                    continue
    except Exception:
        return "Running…", []

    if not events:
        return "Starting…", []

    # task_id -> description
    task_descriptions: dict[str, str] = {}
    # track which tasks have started and which have completed
    started: set[str] = set()
    completed: set[str] = set()

    for e in events:
        payload = e.payload or {}
        tid = (payload.get("task_id") or "").strip()
        ev = getattr(e.type, "value", str(e.type))

        if ev == "task_created" and tid:
            task_descriptions[tid] = (payload.get("description") or "").strip()
        elif ev in ("task_started", "agent_started") and tid:
            started.add(tid)
        elif ev in ("task_completed", "task_failed", "agent_finished") and tid:
            completed.add(tid)

    running_ids = sorted(started - completed)
    total_tasks = len(task_descriptions)
    completed_count = len(completed)

    def _truncate(s: str, max_len: int = 52) -> str:
        s = (s or "").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 1].rstrip() + "…"

    last = events[-1]
    ev_type = getattr(last.type, "value", str(last.type))
    payload = last.payload or {}
    task_id = (payload.get("task_id") or "").strip()
    desc = task_descriptions.get(task_id)

    if ev_type == "swarm_started":
        return "Planning your request…", []
    if ev_type == "planner_started":
        return "Planning your request…", []
    if ev_type == "task_created":
        return f"Planned {total_tasks} task(s). Starting…", []
    if ev_type == "planner_finished":
        n = payload.get("subtask_count", total_tasks) or total_tasks
        tail = f", up to {worker_count} in parallel" if worker_count > 1 else ""
        return f"Executing {n} step(s){tail}…", []
    if ev_type == "executor_started":
        if total_tasks:
            tail = f" (up to {worker_count} in parallel)" if worker_count > 1 else ""
            return f"Executing step 1 of {total_tasks}…{tail}", []
        return "Executing…", []
    if ev_type in ("agent_started", "task_started"):
        step_label = f"Step {completed_count + 1} of {total_tasks}: " if total_tasks else ""
        part = (step_label + _truncate(desc)) if desc else (step_label or "Working on task…")
        if len(running_ids) > 1:
            part += f"  [parallel: {len(running_ids)} tasks]"
        return part.rstrip(": ") or "Working…", running_ids
    if ev_type in ("task_completed", "agent_finished"):
        if total_tasks and completed_count < total_tasks:
            return f"Finished step {completed_count} of {total_tasks}. Next…", running_ids
        return f"Finished step {completed_count} of {total_tasks}. Assembling…", running_ids
    if ev_type == "executor_finished":
        return "Assembling result…", []
    if ev_type == "swarm_finished":
        return "Done.", []

    return "Running…", running_ids
