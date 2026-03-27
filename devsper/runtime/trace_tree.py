"""Build a span-like execution tree from event logs."""

from __future__ import annotations

from pathlib import Path

from devsper.types.event import Event


def _find_log_path(events_dir: str, run_id: str) -> Path | None:
    p = Path(events_dir)
    if not p.exists():
        return None
    direct = p / f"{run_id}.jsonl"
    if direct.is_file():
        return direct
    for f in p.glob("*.jsonl"):
        if f.stem == run_id:
            return f
    return None


def _load_events(path: Path) -> list[Event]:
    out: list[Event] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Event.model_validate_json(line))
        except Exception:
            continue
    out.sort(key=lambda e: e.timestamp)
    return out


def render_trace_for_run(run_id: str, events_dir: str) -> str:
    """Render a tree view for a run from event log entries."""
    path = _find_log_path(events_dir, run_id)
    if path is None:
        return f"No event log found for run_id: {run_id}"
    events = _load_events(path)
    if not events:
        return f"Empty event log for run_id: {run_id}"

    planner_count = 0
    schedule_edges = 0
    task_spans: dict[str, list[str]] = {}
    for e in events:
        t = e.type.value
        p = e.payload or {}
        if t == "task_created":
            planner_count += 1
        if t == "tool_called":
            tid = str(p.get("task_id", ""))
            tool_name = str(p.get("tool", ""))
            if tid:
                task_spans.setdefault(tid, []).append(f"tool.call [{tool_name}]")
        if t in ("task_completed", "task_failed"):
            schedule_edges += 1

    out = [f"swarm.run [{run_id}]"]
    out.append(f"  planner.plan [task_count={planner_count}]")
    out.append(f"  scheduler.schedule [dag_edges={schedule_edges}]")
    for e in events:
        t = e.type.value
        p = e.payload or {}
        if t == "task_started":
            tid = str(p.get("task_id", ""))
            if not tid:
                continue
            out.append(f"  executor.execute [task_id={tid}]")
            out.append("    agent.call")
            for tool_line in task_spans.get(tid, []):
                out.append(f"    {tool_line}")
    return "\n".join(out)
