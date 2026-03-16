"""
Execution telemetry: collect runtime metrics from event log.

Metrics: task_duration, agent_latency, concurrency_levels, task_success_rate.
Emit telemetry summary when swarm finishes.
"""

import os

from devsper.types.event import Event


def _load_events(log_path: str) -> list[Event]:
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


def collect_telemetry(log_path: str) -> dict:
    """
    Collect runtime metrics from an event log.

    Returns a dict with: tasks_completed, tasks_failed, avg_task_duration_seconds,
    avg_agent_latency_seconds, max_concurrency, task_success_rate.
    """
    events_list = _load_events(log_path)
    if not events_list:
        return {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "avg_task_duration_seconds": 0.0,
            "avg_agent_latency_seconds": 0.0,
            "max_concurrency": 0,
            "task_success_rate": 0.0,
        }

    events_list.sort(key=lambda e: e.timestamp)
    task_started = {}
    task_completed = {}
    agent_started = {}
    agent_finished = {}
    concurrency = 0
    max_concurrency = 0

    for e in events_list:
        t = e.timestamp
        payload = e.payload or {}
        task_id = payload.get("task_id")
        typ = e.type.value if hasattr(e.type, "value") else str(e.type)

        if typ == "task_started" and task_id:
            task_started[task_id] = t
            concurrency += 1
            max_concurrency = max(max_concurrency, concurrency)
        elif typ == "task_completed" and task_id:
            task_completed[task_id] = t
            concurrency = max(0, concurrency - 1)
        elif typ == "task_failed" and task_id:
            concurrency = max(0, concurrency - 1)
        elif typ == "agent_started" and task_id:
            agent_started[task_id] = t
        elif typ == "agent_finished" and task_id:
            agent_finished[task_id] = t

    task_durations = []
    for tid, start in task_started.items():
        if tid in task_completed:
            delta = (task_completed[tid] - start).total_seconds()
            task_durations.append(delta)

    agent_latencies = []
    for tid, start in agent_started.items():
        if tid in agent_finished:
            delta = (agent_finished[tid] - start).total_seconds()
            agent_latencies.append(delta)

    completed = len(task_completed)
    failed = sum(1 for e in events_list if (e.type.value if hasattr(e.type, "value") else str(e.type)) == "task_failed")
    total_tasks = completed + failed
    success_rate = (completed / total_tasks) if total_tasks else 0.0

    return {
        "tasks_completed": completed,
        "tasks_failed": failed,
        "avg_task_duration_seconds": round(sum(task_durations) / len(task_durations), 2) if task_durations else 0.0,
        "avg_agent_latency_seconds": round(sum(agent_latencies) / len(agent_latencies), 2) if agent_latencies else 0.0,
        "max_concurrency": max_concurrency,
        "task_success_rate": round(success_rate, 2),
    }


def print_telemetry_summary(log_path: str) -> str:
    """
    Emit telemetry summary to string (e.g. for printing when swarm finishes).

    Example: tasks_completed: 5, avg_task_time: 2.3s, max_concurrency: 3
    """
    m = collect_telemetry(log_path)
    return (
        f"tasks_completed: {m['tasks_completed']}\n"
        f"tasks_failed: {m['tasks_failed']}\n"
        f"avg_task_time: {m['avg_task_duration_seconds']}s\n"
        f"avg_agent_latency: {m['avg_agent_latency_seconds']}s\n"
        f"max_concurrency: {m['max_concurrency']}\n"
        f"task_success_rate: {m['task_success_rate']}"
    )