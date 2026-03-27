from __future__ import annotations

from pathlib import Path

from devsper.runtime.replay_engine import list_run_ids
from devsper.types.event import Event


def _load_events(events_dir: str, run_id: str) -> list[Event]:
    p = Path(events_dir) / f"{run_id}.jsonl"
    if not p.exists():
        return []
    out: list[Event] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Event.model_validate_json(line))
        except Exception:
            continue
    out.sort(key=lambda e: e.timestamp)
    return out


def list_runs(events_dir: str) -> list[dict]:
    out: list[dict] = []
    for rid in list_run_ids(events_dir)[:50]:
        evs = _load_events(events_dir, rid)
        status = "completed" if any(e.type.value == "swarm_finished" for e in evs) else "running"
        out.append({"run_id": rid, "status": status, "event_count": len(evs)})
    return out


def topology_snapshot(events_dir: str, run_id: str) -> dict:
    evs = _load_events(events_dir, run_id)
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    total_cost = 0.0
    for e in evs:
        p = e.payload or {}
        t = e.type.value
        tid = str(p.get("task_id", "") or "")
        if t == "task_created" and tid:
            nodes[tid] = {
                "id": tid,
                "label": str(p.get("description", ""))[:60],
                "type": "task",
                "status": "pending",
                "agent": p.get("agent"),
                "cost_usd": 0.0,
                "duration_ms": 0,
                "model": p.get("model"),
            }
        elif t == "task_started" and tid:
            nodes.setdefault(tid, {"id": tid, "label": tid, "type": "task"})
            nodes[tid]["status"] = "running"
        elif t == "task_completed" and tid:
            nodes.setdefault(tid, {"id": tid, "label": tid, "type": "task"})
            nodes[tid]["status"] = "done"
            c = float(p.get("cost_usd", 0.0) or 0.0)
            nodes[tid]["cost_usd"] = c
            total_cost += c
        elif t == "task_failed" and tid:
            nodes.setdefault(tid, {"id": tid, "label": tid, "type": "task"})
            nodes[tid]["status"] = "failed"

    dag_path = Path(events_dir) / f"{run_id}_dag.json"
    if dag_path.exists():
        try:
            import json

            dag = json.loads(dag_path.read_text(encoding="utf-8"))
            edges = [{"from": str(a), "to": str(b)} for a, b in dag.get("edges", [])]
        except Exception:
            edges = []

    status = "completed" if any(e.type.value == "swarm_finished" for e in evs) else "running"
    if any(e.type.value == "budget_warning" for e in evs):
        status = "budget_stopped"
    return {
        "run_id": run_id,
        "status": status,
        "nodes": list(nodes.values()),
        "edges": edges,
        "summary": {
            "total_cost_usd": total_cost,
            "elapsed_ms": 0,
            "tasks_done": sum(1 for n in nodes.values() if n.get("status") == "done"),
            "tasks_total": len(nodes),
            "tokens_used": 0,
        },
    }
