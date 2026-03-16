"""Test Swarm entrypoint: run(user_task) returns dict[task_id -> result]."""
from unittest.mock import patch

from devsper.swarm.swarm import Swarm
from devsper.types.event import events


MOCK_NUMBERED_RESPONSE = """1. First step
2. Second step
3. Third step
4. Fourth step
5. Fifth step
"""


def test_swarm_run_returns_task_id_to_result():
    """Swarm.run() orchestrates planner → scheduler → executor and returns task_id → result."""
    # Use a task that triggers GENERAL strategy so LLM planner is used (5 steps)
    with (
        patch("devsper.swarm.planner.generate", return_value=MOCK_NUMBERED_RESPONSE),
        patch("devsper.agents.agent.generate", side_effect=["out_1", "out_2", "out_3", "out_4", "out_5"]),
    ):
        swarm = Swarm(worker_count=2, worker_model="gpt-4o", planner_model="gpt-4o")
        result = swarm.run("Summarize swarm intelligence in one paragraph.")

    assert isinstance(result, dict)
    assert len(result) == 5
    assert set(result.values()) == {"out_1", "out_2", "out_3", "out_4", "out_5"}


def test_swarm_emits_swarm_started_and_finished():
    """Swarm emits SWARM_STARTED and SWARM_FINISHED around the pipeline."""
    with (
        patch("devsper.swarm.planner.generate", return_value=MOCK_NUMBERED_RESPONSE),
        patch("devsper.agents.agent.generate", side_effect=["x"] * 5),
    ):
        swarm = Swarm(worker_count=2, worker_model="gpt-4o", planner_model="gpt-4o")
        swarm.run("Summarize in one sentence.")

    recorded = swarm.event_log.read_events()
    types = [e.type for e in recorded]
    assert events.SWARM_STARTED in types
    assert events.SWARM_FINISHED in types


def test_swarm_uses_mock_provider_by_default():
    """Swarm(worker_count=4) with no provider uses MockProvider (no API key)."""
    swarm = Swarm(worker_count=2)
    result = swarm.run("Hello")
    assert isinstance(result, dict)
    assert len(result) == 5
    for v in result.values():
        assert isinstance(v, str) and len(v) > 0
