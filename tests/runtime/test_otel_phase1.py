from datetime import datetime, timezone

from devsper.telemetry.pricing import estimate_cost_usd
from devsper.runtime.trace_tree import render_trace_for_run
from devsper.types.event import Event, events


def test_estimate_cost_usd_known_model():
    # gpt-4o-mini: input 0.15 / 1M, output 0.60 / 1M
    cost = estimate_cost_usd("gpt-4o-mini", 100_000, 50_000)
    assert cost is not None
    assert round(cost, 4) == 0.0450


def test_estimate_cost_usd_unknown_model():
    assert estimate_cost_usd("unknown-model", 100, 100) is None


def test_render_trace_for_run(tmp_path):
    run_id = "run-1"
    p = tmp_path / f"{run_id}.jsonl"
    t = datetime.now(timezone.utc)
    payloads = [
        Event(timestamp=t, type=events.SWARM_STARTED, payload={"user_task": "x"}),
        Event(timestamp=t, type=events.PLANNER_STARTED, payload={"task_id": "root"}),
        Event(timestamp=t, type=events.TASK_CREATED, payload={"task_id": "t1", "description": "do x"}),
        Event(timestamp=t, type=events.EXECUTOR_STARTED, payload={}),
        Event(timestamp=t, type=events.TASK_STARTED, payload={"task_id": "t1"}),
        Event(timestamp=t, type=events.TOOL_CALLED, payload={"task_id": "t1", "tool": "filesystem.list_dir"}),
        Event(timestamp=t, type=events.TASK_COMPLETED, payload={"task_id": "t1"}),
        Event(timestamp=t, type=events.SWARM_FINISHED, payload={"task_count": 1}),
    ]
    p.write_text("\n".join(ev.model_dump_json() for ev in payloads), encoding="utf-8")

    rendered = render_trace_for_run(run_id, str(tmp_path))
    assert "swarm.run" in rendered
    assert "planner.plan" in rendered
    assert "scheduler.schedule" in rendered
    assert "executor.execute [task_id=t1]" in rendered
    assert "tool.call [filesystem.list_dir]" in rendered
