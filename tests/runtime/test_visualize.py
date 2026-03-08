"""Tests for scheduler DAG visualization."""

from hivemind.types.task import Task
from hivemind.swarm.scheduler import Scheduler
from hivemind.runtime.visualize import visualize_scheduler_dag


def test_visualize_empty_scheduler():
    s = Scheduler()
    out = visualize_scheduler_dag(s)
    assert "empty" in out.lower()


def test_visualize_linear_dag():
    tasks = [
        Task(id="task_1", description="Step 1", dependencies=[]),
        Task(id="task_2", description="Step 2", dependencies=["task_1"]),
        Task(id="task_3", description="Step 3", dependencies=["task_2"]),
    ]
    s = Scheduler()
    s.add_tasks(tasks)
    out = visualize_scheduler_dag(s)
    assert "task_1" in out
    assert "task_2" in out
    assert "task_3" in out


def test_visualize_fork_dag():
    tasks = [
        Task(id="task_1", description="Step 1", dependencies=[]),
        Task(id="task_2", description="Step 2", dependencies=["task_1"]),
        Task(id="task_3", description="Step 3", dependencies=["task_1"]),
    ]
    s = Scheduler()
    s.add_tasks(tasks)
    out = visualize_scheduler_dag(s)
    assert "task_1" in out
    assert "task_2" in out
    assert "task_3" in out
