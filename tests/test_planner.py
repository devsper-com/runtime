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
        planner = Planner(model_name="gpt-4o", event_log=log)
        subtasks = planner.plan(task)

    print(subtasks)

    assert len(subtasks) == 5
    assert len(subtasks[0].id) == 8 and subtasks[0].id.isalnum()
    assert subtasks[0].description == "Identify key diffusion model papers"
    assert subtasks[0].dependencies == []

    assert subtasks[1].dependencies == [subtasks[0].id]
    assert subtasks[2].dependencies == [subtasks[1].id]
    assert subtasks[3].dependencies == [subtasks[2].id]
    assert subtasks[4].dependencies == [subtasks[3].id]

    recorded = log.read_events()
    event_types = [e.type for e in recorded]
    expected = (
        [events.PLANNER_STARTED]
        + [events.TASK_CREATED] * 5
        + [events.PLANNER_FINISHED]
    )
    assert event_types == expected, f"Expected {expected}, got {event_types}"
    print("Event sequence:", event_types)


def test_planner_expand_tasks_returns_new_tasks_with_deps():
    """expand_tasks generates follow-up tasks depending on the completed task."""
    from unittest.mock import patch

    completed = Task(
        id="task_2",
        description="Summarize each paper",
        dependencies=["task_1"],
        result="Summary of 5 papers.",
    )
    log = EventLog()
    mock_response = "1. Compare methods\n2. Identify trends\n"
    with patch("hivemind.swarm.planner.generate", return_value=mock_response):
        planner = Planner(model_name="gpt-4o", event_log=log)
        new_tasks = planner.expand_tasks(completed)

    assert len(new_tasks) == 2
    assert len(new_tasks[0].id) == 8 and new_tasks[0].id.isalnum()
    assert new_tasks[0].dependencies == ["task_2"]
    assert new_tasks[1].dependencies == ["task_2"]


if __name__ == "__main__":
    test_planner_emits_lifecycle_and_returns_subtasks()
    test_planner_expand_tasks_returns_new_tasks_with_deps()
    print("Planner test passed.")
