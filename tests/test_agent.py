"""Test agent run flow and event lifecycle."""
from unittest.mock import patch

from devsper.types.task import Task
from devsper.agents.agent import Agent
from devsper.types.event import events
from devsper.utils.event_logger import EventLog


def test_agent_run_emits_lifecycle_events():
    task = Task(id="t1", description="Summarize the document.")
    log = EventLog()
    log.clear()

    with patch("devsper.agents.agent.generate", return_value="Summary output."):
        agent = Agent(model_name="gpt-4o", event_log=log)
        result = agent.run_task(task)

    print("Result:", result)
    assert task.result == result
    assert task.status.value == 2  #

    recorded = log.read_events()
    event_types = [e.type for e in recorded]
    expected = [
        events.AGENT_STARTED,
        events.TASK_STARTED,
        events.TASK_COMPLETED,
        events.AGENT_FINISHED,
    ]
    assert event_types == expected, f"Expected {expected}, got {event_types}"
    print("Event sequence:", event_types)


if __name__ == "__main__":
    test_agent_run_emits_lifecycle_events()
    print("Agents test passed.")
