"""Tests for run analysis: RunReport, cost estimator, run history, pause, inject."""

import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from devsper.types.event import Event, events
from devsper.types.task import TaskStatus
from devsper.intelligence.analysis.run_report import (
    RunReport,
    TaskSummary,
    build_report_from_events,
    _critical_path_and_bottleneck,
)
from devsper.intelligence.analysis.cost_estimator import CostEstimator, MODEL_PRICING
from devsper.runtime.run_history import RunHistory, HISTORY_DB


@pytest.fixture
def events_dir(tmp_path):
    """Create a minimal events file and DAG for a run."""
    run_id = "test_run_001"
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(seconds=1)
    t2 = t0 + timedelta(seconds=3)
    t3 = t0 + timedelta(seconds=5)
    evs = [
        Event(timestamp=t0, type=events.SWARM_STARTED, payload={"user_task": "Root task"}),
        Event(timestamp=t0, type=events.TASK_STARTED, payload={"task_id": "root"}),
        Event(timestamp=t1, type=events.TASK_COMPLETED, payload={"task_id": "root"}),
        Event(timestamp=t1, type=events.TASK_STARTED, payload={"task_id": "a"}),
        Event(timestamp=t2, type=events.TASK_COMPLETED, payload={"task_id": "a"}),
        Event(timestamp=t2, type=events.TASK_STARTED, payload={"task_id": "b"}),
        Event(timestamp=t3, type=events.TASK_FAILED, payload={"task_id": "b", "error": "fail"}),
        Event(timestamp=t3, type=events.SWARM_FINISHED, payload={"task_count": 2}),
    ]
    (tmp_path / f"{run_id}.jsonl").write_text(
        "\n".join(e.model_dump_json() for e in evs), encoding="utf-8"
    )
    dag = {
        "nodes": [
            {"id": "root", "description": "Root"},
            {"id": "a", "description": "Task A"},
            {"id": "b", "description": "Task B"},
        ],
        "edges": [["root", "a"], ["a", "b"]],
    }
    (tmp_path / f"{run_id}_dag.json").write_text(json.dumps(dag), encoding="utf-8")
    return tmp_path


def test_build_report_from_events(events_dir):
    report = build_report_from_events("test_run_001", events_dir)
    assert report.run_id == "test_run_001"
    assert report.root_task == "Root task"
    assert report.total_tasks >= 2
    assert report.completed_tasks >= 1
    assert report.failed_tasks >= 1
    assert report.peak_parallelism >= 1
    assert any(t.task_id == "b" and t.status == TaskStatus.FAILED for t in report.tasks)


def test_critical_path():
    task_ids = ["root", "a", "b"]
    edges = [("root", "a"), ("a", "b")]
    duration_by_task = {"root": 1.0, "a": 3.0, "b": 2.0}
    path, bottleneck = _critical_path_and_bottleneck(task_ids, edges, duration_by_task)
    assert "root" in path
    assert "a" in path
    assert "b" in path
    assert path[0] == "root"
    assert bottleneck is not None


def test_bottleneck_identified():
    task_ids = ["r", "a", "b"]
    edges = [("r", "a"), ("a", "b")]
    duration_by_task = {"r": 1.0, "a": 10.0, "b": 1.0}
    path, bottleneck = _critical_path_and_bottleneck(task_ids, edges, duration_by_task)
    assert bottleneck == "a"


def test_cost_estimate_known_model():
    tasks = [
        TaskSummary("t1", "d", None, TaskStatus.COMPLETED, 1.0, [], [], 1000, 0, None),
    ]
    cost = CostEstimator.estimate(tasks, ["gpt-4o-mini"])
    assert cost is not None
    assert cost >= 0
    assert CostEstimator.format_cost(cost) == f"${cost:.4f}"


def test_cost_estimate_unknown_model():
    tasks = [
        TaskSummary("t1", "d", None, TaskStatus.COMPLETED, 1.0, [], [], 1000, 0, None),
    ]
    cost = CostEstimator.estimate(tasks, ["unknown-model-xyz"])
    assert cost is None
    assert CostEstimator.format_cost(None) == "unknown"


def test_cost_estimate_no_tokens():
    tasks = [
        TaskSummary("t1", "d", None, TaskStatus.COMPLETED, 1.0, [], [], None, 0, None),
    ]
    cost = CostEstimator.estimate(tasks, ["gpt-4o-mini"])
    assert cost is None


def test_run_history_record_and_list(tmp_path):
    db = tmp_path / "runs.db"
    history = RunHistory(db_path=db)
    report = RunReport(
        run_id="r1",
        root_task="task",
        strategy="s",
        started_at="2025-01-01T00:00:00",
        finished_at="2025-01-01T00:01:00",
        total_duration_seconds=60.0,
        total_tasks=3,
        completed_tasks=2,
        failed_tasks=1,
        skipped_tasks=0,
        tasks=[],
        critical_path=[],
        bottleneck_task_id=None,
        tools_called=0,
        tool_success_rate=100.0,
        estimated_cost_usd=0.01,
        models_used=[],
        peak_parallelism=1,
        plain_english_analysis=None,
    )
    history.record_run(report)
    rows = history.list_runs(limit=5)
    assert len(rows) == 1
    assert rows[0].run_id == "r1"
    assert rows[0].root_task == "task"
    assert rows[0].completed_tasks == 2
    assert rows[0].failed_tasks == 1
    got = history.get_run("r1")
    assert got is not None
    assert got.run_id == "r1"
    stats = history.get_stats()
    assert stats["total_runs"] == 1
    assert stats["total_estimated_cost_usd"] == 0.01


def test_runs_cli_output(capsys):
    """Snapshot-style: runs command produces table-like output when no runs."""
    from devsper.cli.main import _run_runs
    class Args:
        run_id = None
        limit = 5
        failed = False
        runs_json = False
    _run_runs(Args())
    out, err = capsys.readouterr()
    assert "No runs" in out or "Run history" in out or "Run ID" in out or out == ""


def test_pause_stops_new_tasks():
    """Executor with pause_event clear should not pick new tasks (we check the loop waits)."""
    import threading
    from devsper.swarm.executor import Executor
    from devsper.swarm.scheduler import Scheduler
    from devsper.types.task import Task, TaskStatus
    from devsper.agents.agent import Agent
    from devsper.utils.event_logger import EventLog

    pause_ev = threading.Event()
    pause_ev.clear()
    scheduler = Scheduler()
    scheduler.add_tasks([
        Task(id="t1", description="T1", dependencies=[]),
    ])
    log = EventLog()
    agent = Agent(model_name="mock", event_log=log)
    executor = Executor(
        scheduler=scheduler,
        agent=agent,
        worker_count=1,
        event_log=log,
        pause_event=pause_ev,
    )
    started = []

    def run_one_task(task):
        started.append(task.id)
        task.result = "ok"
        task.status = TaskStatus.COMPLETED

    import asyncio
    orig_run = agent.run
    def mock_run(task, model_override=None):
        started.append(task.id)
        task.result = "ok"
        task.status = TaskStatus.COMPLETED
    agent.run = mock_run

    async def run_exec():
        await executor.run()

    async def main():
        t = asyncio.create_task(run_exec())
        await asyncio.sleep(0.1)
        assert len(started) == 0
        pause_ev.set()
        await asyncio.sleep(0.2)
        await t
    asyncio.run(main())
    assert "t1" in started


def test_inject_appears_in_memory_context():
    """Injected note (episodic + user_injection tag) is returned by get_memory_context."""
    import tempfile
    from devsper.memory.memory_store import MemoryStore, get_default_store, generate_memory_id
    from devsper.memory.memory_index import MemoryIndex
    from devsper.memory.memory_router import MemoryRouter
    from devsper.memory.memory_types import MemoryRecord, MemoryType

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        store = MemoryStore(db_path=path)
        index = MemoryIndex(store)
        router = MemoryRouter(store=store, index=index, top_k=3)
        record = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.EPISODIC,
            source_task="user_injection",
            content="User said: focus on the API design",
            tags=["user_injection"],
        )
        store.store(record)
        ctx = router.get_memory_context("any task query")
        assert "user_injection" in ctx.lower() or "USER INJECTION" in ctx or "focus on the API" in ctx
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


def test_build_report_from_events_missing_run():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(FileNotFoundError):
            build_report_from_events("nonexistent_run", d)
