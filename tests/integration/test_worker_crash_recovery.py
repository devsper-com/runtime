from devsper.runtime.task_state import TaskStateMachine
from devsper.types.task import Task


class _DummyTask(Task):
    """Use real Task model so TaskStateMachine can read dependencies/status."""


def test_task_requeue_unblocks_ready_after_hitl_wait():
    task = Task(id="t1", description="x", dependencies=[], status=0)
    sm = TaskStateMachine([task])

    # Simulate the controller having transitioned the task into HITL waiting.
    # Must follow valid transitions: PENDING -> READY -> DISPATCHED -> RUNNING -> WAITING.
    _ = sm.get_ready_tasks()  # advances PENDING->READY
    sm.mark_dispatched("t1")
    sm.mark_running("t1")
    sm.mark_waiting("t1")
    assert "t1" not in sm.get_ready_tasks()

    # Simulate worker crash or explicit requeue: task becomes schedulable again.
    sm.requeue("t1")
    ready = sm.get_ready_tasks()
    assert "t1" in ready

