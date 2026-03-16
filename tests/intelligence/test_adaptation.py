"""Tests for self-optimizing swarm adaptation."""

from datetime import datetime, timezone, timedelta

from devsper.types.task import Task, TaskStatus
from devsper.swarm.scheduler import Scheduler
from devsper.intelligence.adaptation import (
    detect_slow_tasks,
    detect_failed_tasks,
    suggest_alternative_tasks,
    create_alternative_subtasks_for_failed,
)


def test_detect_failed_tasks():
    s = Scheduler()
    t1 = Task(id="t1", description="One", dependencies=[])
    t2 = Task(id="t2", description="Two", dependencies=["t1"])
    s.add_tasks([t1, t2])
    s.mark_failed("t1")
    failed = detect_failed_tasks(s)
    assert "t1" in failed
    assert "t2" not in failed


def test_detect_slow_tasks():
    s = Scheduler()
    t1 = Task(id="t1", description="One", dependencies=[])
    s.add_tasks([t1])
    t1.status = TaskStatus.RUNNING
    start = datetime.now(timezone.utc) - timedelta(seconds=65)
    task_start_times = {"t1": start}
    slow = detect_slow_tasks(s, task_start_times, threshold_seconds=60.0)
    assert "t1" in slow


def test_detect_slow_tasks_not_slow():
    s = Scheduler()
    t1 = Task(id="t1", description="One", dependencies=[])
    s.add_tasks([t1])
    t1.status = TaskStatus.RUNNING
    start = datetime.now(timezone.utc) - timedelta(seconds=30)
    task_start_times = {"t1": start}
    slow = detect_slow_tasks(s, task_start_times, threshold_seconds=60.0)
    assert "t1" not in slow


def test_suggest_alternative_tasks_without_planner_returns_empty():
    task = Task(id="t1", description="Fail", dependencies=[], status=TaskStatus.FAILED)
    alt = suggest_alternative_tasks(task, None)
    assert alt == []


def test_create_alternative_subtasks_for_failed_returns_list():
    s = Scheduler()
    t1 = Task(id="t1", description="One", dependencies=[], status=TaskStatus.FAILED)
    s.add_tasks([t1])
    planner = None
    alt = create_alternative_subtasks_for_failed(t1, planner, s)
    assert isinstance(alt, list)
