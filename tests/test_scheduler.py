"""Test scheduler: task DAG, get_ready_tasks, mark_completed, is_finished."""
from hivemind.types.task import Task, TaskStatus
from hivemind.swarm.scheduler import Scheduler


def _make_chain() -> list[Task]:
    """Five tasks in a chain: task_1 → task_2 → task_3 → task_4 → task_5."""
    return [
        Task(id="task_1", description="First", dependencies=[]),
        Task(id="task_2", description="Second", dependencies=["task_1"]),
        Task(id="task_3", description="Third", dependencies=["task_2"]),
        Task(id="task_4", description="Fourth", dependencies=["task_3"]),
        Task(id="task_5", description="Fifth", dependencies=["task_4"]),
    ]


def test_scheduler_ready_progression():
    """Add chain of tasks; get_ready_tasks returns one at a time; mark_completed unlocks next."""
    tasks = _make_chain()
    scheduler = Scheduler()
    scheduler.add_tasks(tasks)

    assert not scheduler.is_finished()

    # Only task_1 has no dependencies → ready
    ready = scheduler.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "task_1"
    assert ready[0].status == TaskStatus.PENDING

    scheduler.mark_completed("task_1")
    ready = scheduler.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "task_2"

    scheduler.mark_completed("task_2")
    ready = scheduler.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "task_3"

    scheduler.mark_completed("task_3")
    ready = scheduler.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "task_4"

    scheduler.mark_completed("task_4")
    ready = scheduler.get_ready_tasks()
    assert len(ready) == 1
    assert ready[0].id == "task_5"

    scheduler.mark_completed("task_5")
    ready = scheduler.get_ready_tasks()
    assert len(ready) == 0
    assert scheduler.is_finished()


if __name__ == "__main__":
    test_scheduler_ready_progression()
    print("Scheduler test passed.")
