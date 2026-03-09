"""Tests for v1.9: serialization, bus, stateless executor, scheduler snapshot/restore, checkpointer, health."""

import asyncio
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import Event, events
from hivemind.types.exceptions import EventSerializationError, TaskNotFoundError
from hivemind.agents.agent import Agent, AgentRequest, AgentResponse
from hivemind.bus.message import BusMessage, create_bus_message
from hivemind.bus.backends.memory import InMemoryBus
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.checkpointer import SchedulerCheckpointer
from hivemind.runtime.health import HealthChecker, HealthReport


def test_task_serialization_roundtrip():
    task = Task(
        id="t1",
        description="Do something",
        dependencies=["root"],
        status=TaskStatus.COMPLETED,
        result="done",
        error=None,
        role="research",
        retry_count=1,
    )
    restored = Task.from_dict(task.to_dict())
    assert restored.id == task.id
    assert restored.description == task.description
    assert restored.dependencies == task.dependencies
    assert restored.status == task.status
    assert restored.result == task.result
    assert restored.error == task.error
    assert restored.role == task.role
    assert restored.retry_count == task.retry_count
    assert Task.from_json(task.to_json()).id == task.id


def test_event_payload_must_be_json_safe():
    from datetime import datetime, timezone
    with pytest.raises(EventSerializationError):
        Event(
            timestamp=datetime.now(timezone.utc),
            type=events.TASK_STARTED,
            payload={"bad": object()},
        )
    # OK
    e = Event(timestamp=datetime.now(timezone.utc), type=events.TASK_STARTED, payload={"task_id": "t1"})
    assert e.to_dict()["payload"] == {"task_id": "t1"}


def test_agent_request_response_roundtrip():
    task = Task(id="t1", description="x", dependencies=[])
    req = AgentRequest(
        task=task,
        memory_context="ctx",
        tools=["tool_a"],
        model="gpt-4o",
        system_prompt="You are helpful.",
        prefetch_used=True,
    )
    restored_req = AgentRequest.from_dict(req.to_dict())
    assert restored_req.task.id == req.task.id
    assert restored_req.memory_context == req.memory_context
    assert restored_req.tools == req.tools
    assert restored_req.model == req.model
    assert restored_req.prefetch_used == req.prefetch_used

    resp = AgentResponse(
        task_id="t1",
        result="ok",
        tools_called=["tool_a"],
        broadcasts=[],
        tokens_used=100,
        duration_seconds=1.5,
        error=None,
        success=True,
    )
    restored_resp = AgentResponse.from_dict(resp.to_dict())
    assert restored_resp.task_id == resp.task_id
    assert restored_resp.result == resp.result
    assert restored_resp.tools_called == resp.tools_called
    assert restored_resp.tokens_used == resp.tokens_used
    assert restored_resp.duration_seconds == resp.duration_seconds
    assert restored_resp.success == resp.success


def test_inmemory_bus_wildcard():
    async def _run():
        bus = InMemoryBus()
        await bus.start()
        received = []

        async def handler(msg: BusMessage):
            received.append(msg.topic)

        await bus.subscribe("task.*", handler)
        await bus.publish(create_bus_message(topic="task.ready", payload={}))
        await bus.publish(create_bus_message(topic="task.completed", payload={}))
        await bus.publish(create_bus_message(topic="other.topic", payload={}))
        await asyncio.sleep(0.02)
        assert "task.ready" in received
        assert "task.completed" in received
        assert "other.topic" not in received
        await bus.stop()

    asyncio.run(_run())


def test_inmemory_bus_publish_order():
    async def _run():
        bus = InMemoryBus()
        await bus.start()
        order = []

        async def h1(msg):
            order.append(1)

        async def h2(msg):
            order.append(2)

        await bus.subscribe("test", h1)
        await bus.subscribe("test", h2)
        await bus.publish(create_bus_message(topic="test", payload={}))
        await asyncio.sleep(0.02)
        assert order == [1, 2]
        await bus.stop()

    asyncio.run(_run())


def test_executor_holds_no_state():
    from hivemind.swarm.executor import Executor
    from hivemind.agents.agent import Agent
    from hivemind.utils.event_logger import EventLog
    from hivemind.types.task import Task

    log = EventLog()
    task = Task(id="root", description="Quick task", dependencies=[])
    scheduler = Scheduler()
    scheduler.add_tasks([task])
    with patch("hivemind.agents.agent.generate", return_value="Done."):
        agent = Agent(model_name="mock", event_log=log)
        executor = Executor(scheduler=scheduler, agent=agent, worker_count=1, event_log=log)
        executor.run_sync()
    assert not hasattr(executor, "_results") or getattr(executor, "_results", None) is None
    results = scheduler.get_results()
    assert "root" in results
    assert results["root"] == "Done."


def test_scheduler_snapshot_restore():
    t1 = Task(id="a", description="d1", dependencies=[])
    t2 = Task(id="b", description="d2", dependencies=["a"])
    s = Scheduler(run_id="run1")
    s.add_tasks([t1, t2])
    s.mark_completed("a", "result_a")
    snap = s.snapshot()
    assert snap["run_id"] == "run1"
    assert "tasks" in snap
    assert "edges" in snap
    assert snap["completed_count"] == 1
    restored = Scheduler.restore(snap)
    assert restored.run_id == s.run_id
    assert len(restored.get_all_tasks()) == 2
    assert restored.get_results().get("a") == "result_a"
    assert restored.get_ready_tasks()
    task_b = restored.get_task("b")
    assert task_b.description == "d2"


def test_scheduler_get_task_raises():
    s = Scheduler()
    s.add_tasks([Task(id="x", description="y", dependencies=[])])
    s.get_task("x")
    with pytest.raises(TaskNotFoundError):
        s.get_task("nonexistent")


def test_checkpointer_writes_on_interval():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        events_dir = tempfile.mkdtemp()
        ckp = SchedulerCheckpointer(events_dir=events_dir, interval_tasks=2)
        s = Scheduler(run_id="test_run_interval")
        s.add_tasks([
            Task(id="1", description="d1", dependencies=[]),
            Task(id="2", description="d2", dependencies=[]),
        ])
        ckp.on_task_completed(s)
        ckp.on_task_completed(s)
        checkpoint_path = os.path.join(events_dir, "test_run_interval.checkpoint.json")
        assert os.path.isfile(checkpoint_path)
        with open(checkpoint_path) as f:
            data = json.load(f)
        assert data["run_id"] == "test_run_interval"
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass
        try:
            for f in os.listdir(events_dir):
                os.unlink(os.path.join(events_dir, f))
            os.rmdir(events_dir)
        except Exception:
            pass


def test_checkpointer_atomic_write():
    events_dir = tempfile.mkdtemp()
    try:
        ckp = SchedulerCheckpointer(events_dir=events_dir)
        s = Scheduler(run_id="atomic_run")
        s.add_tasks([Task(id="1", description="d", dependencies=[])])
        ckp.write_now(s)
        path = os.path.join(events_dir, "atomic_run.checkpoint.json")
        assert os.path.isfile(path)
        with open(path) as f:
            data = json.load(f)
        assert data["run_id"] == "atomic_run"
        assert "tasks" in data
    finally:
        for f in os.listdir(events_dir):
            os.unlink(os.path.join(events_dir, f))
        os.rmdir(events_dir)


def test_health_check_all_pass():
    from hivemind.config.schema import HivemindConfigModel
    cfg = HivemindConfigModel()
    checker = HealthChecker()
    report = asyncio.run(checker.check(cfg))
    assert isinstance(report, HealthReport)
    assert "bus_reachable" in report.checks
    assert report.checks["bus_reachable"] is True
    assert report.timestamp
    healthy = all(report.checks.values())
    if report.checks.get("memory_store_readable", True) and report.checks.get("tool_scores_readable", True):
        assert healthy or report.errors


def test_health_check_partial_fail():
    from hivemind.config.schema import HivemindConfigModel
    cfg = HivemindConfigModel()
    checker = HealthChecker()
    report = asyncio.run(checker.check(cfg))
    if not all(report.checks.values()):
        assert report.healthy is False
        assert report.errors
