"""Test planner: one task → list of subtasks with sequential dependencies."""
from unittest.mock import patch

from hivemind.types.task import Task
from hivemind.swarm.planner import Planner
from hivemind.types.event import events
from hivemind.utils.event_logger import EventLog


MOCK_NUMBERED_RESPONSE = """1. Identify key diffusion model papers
2. Summarize each paper
3. Extract architectural components
4. Compare improvements across papers
5. Produce synthesis
"""


def test_planner_emits_lifecycle_and_returns_subtasks():
    task = Task(id="root", description="Analyze diffusion model research")
    log = EventLog()
    log.clear()

    with patch("hivemind.swarm.planner.generate", return_value=MOCK_NUMBERED_RESPONSE):
        planner = Planner(model_name="default", event_log=log)
        subtasks = planner.plan(task)

    print(subtasks)

    assert len(subtasks) == 5
    assert subtasks[0].id == "task_1"
    assert subtasks[0].description == "Identify key diffusion model papers"
    assert subtasks[0].dependencies == []

    assert subtasks[1].id == "task_2"
    assert subtasks[1].dependencies == ["task_1"]

    assert subtasks[2].id == "task_3"
    assert subtasks[2].dependencies == ["task_2"]

    assert subtasks[3].id == "task_4"
    assert subtasks[3].dependencies == ["task_3"]

    assert subtasks[4].id == "task_5"
    assert subtasks[4].dependencies == ["task_4"]

    recorded = log.read_events()
    event_types = [e.type for e in recorded]
    expected = (
        [events.PLANNER_STARTED]
        + [events.TASK_CREATED] * 5
        + [events.PLANNER_FINISHED]
    )
    assert event_types == expected, f"Expected {expected}, got {event_types}"
    print("Event sequence:", event_types)


if __name__ == "__main__":
    test_planner_emits_lifecycle_and_returns_subtasks()
    print("Planner test passed.")
