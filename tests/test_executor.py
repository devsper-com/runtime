"""Test executor: planner → tasks, scheduler → graph, executor runs tasks to completion."""
from unittest.mock import patch

from hivemind.types.task import Task, TaskStatus
from hivemind.swarm.planner import Planner
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.executor import Executor
from hivemind.agents.agent import Agent
from hivemind.utils.event_logger import EventLog
from hivemind.types.event import events


MOCK_NUMBERED_RESPONSE = """1. First step
2. Second step
3. Third step
4. Fourth step
5. Fifth step
"""


def test_executor_completes_all_tasks():
    """Planner produces tasks → scheduler holds graph → executor runs until finished."""
    log = EventLog()
    task = Task(id="root", description="Run a small pipeline")

    with (
        patch("hivemind.swarm.planner.generate", return_value=MOCK_NUMBERED_RESPONSE),
        patch("hivemind.agents.agent.generate", side_effect=["Completed."] * 5),
    ):
        planner = Planner(model_name="gpt-4o", event_log=log)
        subtasks = planner.plan(task)

        assert len(subtasks) == 5

        scheduler = Scheduler()
        scheduler.add_tasks(subtasks)
        assert not scheduler.is_finished()

        agent = Agent(model_name="gpt-4o", event_log=log)
        executor = Executor(
            scheduler=scheduler,
            agent=agent,
            worker_count=2,
            event_log=log,
        )
        executor.run_sync()

    assert scheduler.is_finished()
    for t in subtasks:
        assert t.status == TaskStatus.COMPLETED
        assert t.result is not None

    recorded = log.read_events()
    event_types = [e.type for e in recorded]
    assert events.EXECUTOR_STARTED in event_types
    assert events.EXECUTOR_FINISHED in event_types


if __name__ == "__main__":
    test_executor_completes_all_tasks()
    print("Executor test passed.")
