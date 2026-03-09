"""
RunReport and TaskSummary dataclasses; build from event log and DAG.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from hivemind.types.event import Event, events
from hivemind.types.task import TaskStatus


@dataclass
class TaskSummary:
    task_id: str
    description: str
    role: str | None
    status: TaskStatus
    duration_seconds: float
    tools_used: list[str]
    tool_failures: list[str]
    tokens_used: int | None
    retry_count: int
    error: str | None


@dataclass
class RunReport:
    run_id: str
    root_task: str
    strategy: str
    started_at: str
    finished_at: str
    total_duration_seconds: float
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    skipped_tasks: int
    tasks: list[TaskSummary]
    critical_path: list[str]
    bottleneck_task_id: str | None
    tools_called: int
    tool_success_rate: float
    estimated_cost_usd: float | None
    models_used: list[str]
    peak_parallelism: int
    plain_english_analysis: str | None


def _find_log_path(events_dir: str | Path, run_id: str) -> str | None:
    """Find events JSONL file for run_id. Returns path or None."""
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


def _load_dag(events_dir: str | Path, run_id: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Load DAG from events_dir / {run_id}_dag.json. Returns (nodes, edges)."""
    path = Path(events_dir) / f"{run_id}_dag.json"
    if not path.is_file():
        return [], []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes", [])
    edges = [tuple(e) for e in data.get("edges", [])]
    return nodes, edges


def _critical_path_and_bottleneck(
    task_ids: list[str],
    edges: list[tuple[str, str]],
    duration_by_task: dict[str, float],
) -> tuple[list[str], str | None]:
    """
    Compute critical path (longest dependency chain by duration) and bottleneck task.
    edges: (from_id, to_id) meaning from is dependency of to.
    """
    if not task_ids:
        return [], None
    pred = {tid: [] for tid in task_ids}
    succ = {tid: [] for tid in task_ids}
    for a, b in edges:
        if a in pred and b in succ:
            pred[b].append(a)
            succ[a].append(b)
    # Topological order (roots first)
    in_degree = {tid: len(pred[tid]) for tid in task_ids}
    order = []
    stack = [tid for tid in task_ids if in_degree[tid] == 0]
    while stack:
        n = stack.pop()
        order.append(n)
        for s in succ[n]:
            in_degree[s] -= 1
            if in_degree[s] == 0:
                stack.append(s)
    # Longest path from any root to each node (earliest finish)
    dist = {tid: duration_by_task.get(tid, 0.0) for tid in task_ids}
    for n in order:
        for p in pred[n]:
            dist[n] = max(dist[n], dist[p] + duration_by_task.get(n, 0.0))
    # Longest path value and a leaf on that path
    max_dist = max(dist.values()) if dist else 0.0
    leaf = next((tid for tid in order if dist[tid] == max_dist), None)
    if not leaf:
        return list(order), None
    # Backtrack to get critical path (path from root to leaf with max total duration)
    path = []
    cur = leaf
    while cur is not None:
        path.append(cur)
        best_pred = None
        best_val = -1.0
        for p in pred[cur]:
            v = dist.get(p, 0.0)
            if v >= best_val:
                best_val = v
                best_pred = p
        cur = best_pred
    path.reverse()
    # Bottleneck: task on critical path with highest single-task duration
    bottleneck = None
    bottleneck_dur = -1.0
    for tid in path:
        d = duration_by_task.get(tid, 0.0)
        if d > bottleneck_dur:
            bottleneck_dur = d
            bottleneck = tid
    return path, bottleneck


def build_report_from_events(run_id: str, events_dir: str | Path) -> RunReport:
    """
    Load events from {events_dir}/{run_id}.jsonl (or matching .jsonl), reconstruct
    timeline, compute critical path and bottleneck, peak parallelism, and cost estimate.
    """
    events_dir = Path(events_dir)
    log_path = _find_log_path(events_dir, run_id)
    if not log_path:
        raise FileNotFoundError(f"No event log found for run_id: {run_id!r} (looked in {events_dir})")
    evs = _load_events(log_path)
    if not evs:
        raise ValueError(f"Empty event log for run_id: {run_id!r}")

    evs.sort(key=lambda e: e.timestamp)
    nodes, edges = _load_dag(events_dir, run_id)
    node_by_id = {n["id"]: n for n in nodes}
    # Timeline: TASK_STARTED -> TASK_COMPLETED / TASK_FAILED
    task_started: dict[str, float] = {}
    task_ended: dict[str, float] = {}
    task_status: dict[str, str] = {}
    task_error: dict[str, str] = {}
    tools_by_task: dict[str, list[str]] = {}
    tool_failures_by_task: dict[str, list[str]] = {}
    root_task = ""
    started_ts: str | None = None
    finished_ts: str | None = None
    strategy = ""

    for e in evs:
        typ = e.type.value if hasattr(e.type, "value") else str(e.type)
        payload = e.payload or {}
        task_id = (payload.get("task_id") or "").strip()
        ts = e.timestamp
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)

        if typ == "swarm_started":
            root_task = (payload.get("user_task") or "")[:500]
            if not started_ts:
                started_ts = ts_str
        elif typ == "task_started" and task_id:
            task_started[task_id] = ts.timestamp() if hasattr(ts, "timestamp") else 0.0
        elif typ == "task_completed" and task_id:
            task_ended[task_id] = ts.timestamp() if hasattr(ts, "timestamp") else 0.0
            task_status[task_id] = "completed"
        elif typ == "task_failed" and task_id:
            task_ended[task_id] = ts.timestamp() if hasattr(ts, "timestamp") else 0.0
            task_status[task_id] = "failed"
            task_error[task_id] = payload.get("error") or "Unknown error"
        elif typ == "tool_called" and task_id:
            tool = payload.get("tool") or "unknown"
            tools_by_task.setdefault(task_id, []).append(tool)
        elif typ == "swarm_finished":
            finished_ts = ts_str

    if not started_ts:
        started_ts = evs[0].timestamp.isoformat() if evs else ""
    if not finished_ts:
        finished_ts = evs[-1].timestamp.isoformat() if evs else ""

    # All task ids from DAG + any from events not in DAG
    all_task_ids = set(node_by_id.keys()) | set(task_started.keys()) | set(task_ended.keys())
    duration_by_task: dict[str, float] = {}
    for tid in all_task_ids:
        start = task_started.get(tid)
        end = task_ended.get(tid)
        if start is not None and end is not None:
            duration_by_task[tid] = max(0.0, end - start)
        else:
            duration_by_task[tid] = 0.0

    critical_path, bottleneck_task_id = _critical_path_and_bottleneck(
        list(all_task_ids), edges, duration_by_task
    )

    # Peak parallelism: max overlapping RUNNING windows
    intervals: list[tuple[float, float]] = []
    for tid in all_task_ids:
        s = task_started.get(tid)
        e = task_ended.get(tid)
        if s is not None and e is not None:
            intervals.append((s, e))
    peak_parallelism = 0
    if intervals:
        points = []
        for a, b in intervals:
            points.append((a, 1))
            points.append((b, -1))
        points.sort(key=lambda x: (x[0], -x[1]))
        cur = 0
        for _t, delta in points:
            cur += delta
            peak_parallelism = max(peak_parallelism, cur)

    # Build TaskSummary list (order: by first appearance in events / DAG)
    seen = set()
    task_order = []
    for e in evs:
        p = e.payload or {}
        tid = (p.get("task_id") or "").strip()
        if tid and tid not in seen and (tid in node_by_id or tid in task_status):
            seen.add(tid)
            task_order.append(tid)
    for nid in node_by_id:
        if nid not in seen:
            task_order.append(nid)
            seen.add(nid)

    status_enum = {
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
        "running": TaskStatus.RUNNING,
        "pending": TaskStatus.PENDING,
    }
    tasks_list: list[TaskSummary] = []
    for tid in task_order:
        desc = (node_by_id.get(tid) or {}).get("description") or tid
        st = task_status.get(tid, "pending")
        if tid not in task_started and tid not in task_ended and tid in node_by_id:
            st = "skipped"
        status = status_enum.get(st, TaskStatus.PENDING)
        dur = duration_by_task.get(tid, 0.0)
        tools = list(tools_by_task.get(tid, []))
        tool_failures = list(tool_failures_by_task.get(tid, []))
        tasks_list.append(
            TaskSummary(
                task_id=tid,
                description=desc,
                role=None,
                status=status,
                duration_seconds=dur,
                tools_used=tools,
                tool_failures=tool_failures,
                tokens_used=None,
                retry_count=0,
                error=task_error.get(tid),
            )
        )

    completed_tasks = sum(1 for t in tasks_list if t.status == TaskStatus.COMPLETED)
    failed_tasks = sum(1 for t in tasks_list if t.status == TaskStatus.FAILED)
    total_tasks = len(tasks_list)
    skipped_tasks = max(0, total_tasks - completed_tasks - failed_tasks)

    tools_called = sum(len(t.tools_used) for t in tasks_list)
    tool_fail_count = sum(len(t.tool_failures) for t in tasks_list)
    tool_success_rate = (
        (100.0 * (tools_called - tool_fail_count) / tools_called)
        if tools_called else 100.0
    )

    total_duration_seconds = 0.0
    if evs:
        t0 = evs[0].timestamp
        t1 = evs[-1].timestamp
        total_duration_seconds = (t1 - t0).total_seconds() if hasattr(t0, "__sub__") else 0.0

    # Cost estimate
    from hivemind.intelligence.analysis.cost_estimator import CostEstimator
    estimated_cost_usd = CostEstimator.estimate(tasks_list, [])

    return RunReport(
        run_id=run_id,
        root_task=root_task or "unknown",
        strategy=strategy or "unknown",
        started_at=started_ts or "",
        finished_at=finished_ts or "",
        total_duration_seconds=max(0.0, total_duration_seconds),
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        failed_tasks=failed_tasks,
        skipped_tasks=skipped_tasks,
        tasks=tasks_list,
        critical_path=critical_path,
        bottleneck_task_id=bottleneck_task_id,
        tools_called=tools_called,
        tool_success_rate=tool_success_rate,
        estimated_cost_usd=estimated_cost_usd,
        models_used=[],
        peak_parallelism=peak_parallelism,
        plain_english_analysis=None,
    )
