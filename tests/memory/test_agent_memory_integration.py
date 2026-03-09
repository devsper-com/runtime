"""Tests for agent memory integration (retrieve, inject, optional store)."""
from unittest.mock import patch, MagicMock
import os
import tempfile

import pytest

from hivemind.types.task import Task
from hivemind.agents.agent import Agent
from hivemind.utils.event_logger import EventLog
from hivemind.memory.memory_router import MemoryRouter
from hivemind.memory.memory_store import MemoryStore, get_default_store
from hivemind.memory.memory_index import MemoryIndex


@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = MemoryStore(db_path=path)
    yield store
    try:
        os.unlink(path)
    except Exception:
        pass


def test_agent_run_without_memory_router_unchanged():
    """Without memory_router, agent behavior is unchanged (no RELEVANT MEMORY in prompt)."""
    task = Task(id="t1", description="Do something.")
    log = EventLog()
    with patch("hivemind.agents.agent.generate", return_value="Done.") as m:
        agent = Agent(model_name="mock", event_log=log)
        result = agent.run_task(task)
    assert result == "Done."
    assert m.called


def test_agent_run_with_memory_router_injects_context(temp_store):
    """With memory_router, agent receives RELEVANT MEMORY in prompt."""
    task = Task(id="t1", description="Analyze diffusion models.")
    log = EventLog()
    index = MemoryIndex(temp_store)
    router = MemoryRouter(store=temp_store, index=index, top_k=5)
    with patch("hivemind.agents.agent.generate", return_value="Analysis done.") as m:
        agent = Agent(model_name="mock", event_log=log, memory_router=router)
        result = agent.run_task(task)
    assert result == "Analysis done."
    call_args = m.call_args[0]
    prompt = call_args[1]
    assert "Analyze diffusion models" in prompt or "task_description" in str(m.call_args)


def test_agent_store_result_to_memory(temp_store):
    """With store_result_to_memory=True and memory_router with store, result is stored."""
    task = Task(id="t1", description="Compute 2+2.")
    log = EventLog()
    router = MemoryRouter(store=temp_store, index=MemoryIndex(temp_store))
    with patch("hivemind.agents.agent.generate", return_value="4"):
        agent = Agent(
            model_name="mock",
            event_log=log,
            memory_router=router,
            store_result_to_memory=True,
        )
        agent.run_task(task)
    listed = temp_store.list_memory(limit=10)
    assert len(listed) >= 1
    assert any("4" in r.content for r in listed)
