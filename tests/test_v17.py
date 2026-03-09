"""Tests for v1.7: Critic loop, agent messaging, speculative prefetching, structured output self-correction."""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hivemind.agents.critic import CriticAgent, CritiqueResult
from hivemind.agents.message_bus import SwarmMessageBus, AgentMessage
from hivemind.types.task import Task, TaskStatus
from hivemind.types.event import events
from hivemind.utils.event_logger import EventLog
from hivemind.workflow.runner import (
    WorkflowStepError,
    try_parse_structured,
    _format_schema,
    _strip_markdown_json,
)
from hivemind.workflow.schema import OutputField, WorkflowDefinition, WorkflowStep


# --- Critic ---


def test_critic_triggers_retry_below_threshold():
    """Mock critique score 0.5 → task re-queued (executor logic)."""
    from hivemind.swarm.executor import Executor
    from hivemind.swarm.scheduler import Scheduler
    from hivemind.agents.agent import Agent

    log = EventLog()
    scheduler = Scheduler()
    task = Task(
        id="t1",
        description="Analyze X",
        dependencies=[],
        role="research",
        retry_count=0,
    )
    scheduler.add_tasks([task])

    critic = CriticAgent(event_log=log)
    with patch.object(critic, "critique", new_callable=AsyncMock) as mock_critique:
        mock_critique.return_value = CritiqueResult(
            score=0.5,
            issues=["Incomplete"],
            retry=True,
            raw="{}",
        )
        with patch.object(critic, "get_retry_prompt", new_callable=AsyncMock) as mock_retry:
            mock_retry.return_value = "Analyze X\n\n--- Critique ---\nIncomplete"

            agent = Agent(model_name="mock", event_log=log)
            executor = Executor(
                scheduler=scheduler,
                agent=agent,
                worker_count=1,
                event_log=log,
                critic_agent=critic,
                critic_enabled=True,
                critic_roles=["research", "analysis", "code"],
                fast_model="mock",
            )
            with patch("hivemind.agents.agent.generate", side_effect=["first", "second"]):
                asyncio.run(executor.run())

            assert mock_critique.called
            assert task.retry_count == 1
            assert task.status == TaskStatus.COMPLETED
            recorded = [e.type for e in log.read_events()]
            assert events.TASK_CRITIQUED in recorded


def test_critic_no_retry_above_threshold():
    """Score 0.85 → no retry."""
    from hivemind.swarm.executor import Executor
    from hivemind.swarm.scheduler import Scheduler
    from hivemind.agents.agent import Agent

    log = EventLog()
    scheduler = Scheduler()
    task = Task(
        id="t1",
        description="Analyze X",
        dependencies=[],
        role="research",
        retry_count=0,
    )
    scheduler.add_tasks([task])

    critic = CriticAgent(event_log=log)
    with patch.object(critic, "critique", new_callable=AsyncMock) as mock_critique:
        mock_critique.return_value = CritiqueResult(
            score=0.85,
            issues=[],
            retry=False,
            raw="{}",
        )
        agent = Agent(model_name="mock", event_log=log)
        executor = Executor(
            scheduler=scheduler,
            agent=agent,
            worker_count=1,
            event_log=log,
            critic_agent=critic,
            critic_enabled=True,
            critic_roles=["research"],
            fast_model="mock",
        )
        with patch("hivemind.agents.agent.generate", return_value="result"):
            asyncio.run(executor.run())

        assert mock_critique.called
        assert task.retry_count == 0
        assert task.status == TaskStatus.COMPLETED


def test_critic_max_one_retry():
    """Already-retried task not critiqued again (retry_count >= 1 skips retry)."""
    from hivemind.swarm.executor import Executor
    from hivemind.swarm.scheduler import Scheduler
    from hivemind.agents.agent import Agent

    log = EventLog()
    scheduler = Scheduler()
    task = Task(
        id="t1",
        description="Analyze X",
        dependencies=[],
        role="research",
        retry_count=1,  # already retried
    )
    scheduler.add_tasks([task])

    critic = CriticAgent(event_log=log)
    with patch.object(critic, "critique", new_callable=AsyncMock) as mock_critique:
        agent = Agent(model_name="mock", event_log=log)
        executor = Executor(
            scheduler=scheduler,
            agent=agent,
            worker_count=1,
            event_log=log,
            critic_agent=critic,
            critic_enabled=True,
            critic_roles=["research"],
            fast_model="mock",
        )
        with patch("hivemind.agents.agent.generate", return_value="result"):
            asyncio.run(executor.run())

        assert not mock_critique.called
        assert task.retry_count == 1


# --- Message bus ---


def test_message_bus_broadcast_received():
    """Agent B receives agent A's broadcast via get_context."""
    bus = SwarmMessageBus()
    bus.broadcast_sync("task_a", "Finding: X is true.", tags=[])
    bus.broadcast_sync("task_b", "Finding: Y is false.", tags=[])
    ctx = bus.get_context_sync("task_c", max_messages=5)
    assert "task_a" in ctx
    assert "task_b" in ctx
    assert "X is true" in ctx
    assert "Y is false" in ctx


def test_message_bus_excludes_own_messages():
    """Agent doesn't see its own broadcasts in get_context."""
    bus = SwarmMessageBus()
    bus.broadcast_sync("task_a", "From A", tags=[])
    bus.broadcast_sync("task_b", "From B", tags=[])
    ctx = bus.get_context_sync("task_a", max_messages=5)
    assert "From B" in ctx
    assert "From A" not in ctx


# --- Prefetcher ---


def test_prefetch_consumed_on_task_start():
    """Prefetch result used; memory not re-fetched (executor passes prefetch_result to agent)."""
    from hivemind.swarm.prefetcher import TaskPrefetcher, PrefetchResult
    from hivemind.agents.agent import Agent
    from hivemind.types.task import Task

    memory_router = MagicMock()
    memory_router.get_memory_context = MagicMock(return_value="cached memory")
    tool_selector = MagicMock(return_value=[])
    prefetcher = TaskPrefetcher(
        memory_router=memory_router,
        tool_selector=tool_selector,
        max_age_seconds=30.0,
    )
    task = Task(id="t1", description="Do something", dependencies=[])
    asyncio.run(prefetcher.prefetch(task))
    result = prefetcher.consume("t1")
    assert result is not None
    assert result.memory_context == "cached memory"
    assert result.tools == []

    log = EventLog()
    agent = Agent(model_name="mock", event_log=log, memory_router=memory_router)
    with patch("hivemind.agents.agent.generate", return_value="done"):
        agent.run(task, prefetch_result=result)
    assert task.result == "done"
    # Only one call (from prefetcher.prefetch); agent must not call memory_router when using prefetch_result
    assert memory_router.get_memory_context.call_count == 1


def test_prefetch_stale_result_ignored():
    """Result > 30s old not used (consume returns None)."""
    from hivemind.swarm.prefetcher import TaskPrefetcher, PrefetchResult

    prefetcher = TaskPrefetcher(
        memory_router=MagicMock(),
        tool_selector=MagicMock(return_value=[]),
        max_age_seconds=30.0,
    )
    old = datetime.now(timezone.utc) - timedelta(seconds=40)
    prefetcher._warmup_cache["t1"] = PrefetchResult(
        memory_context="x",
        tools=[],
        computed_at=old,
    )
    result = prefetcher.consume("t1")
    assert result is None


# --- Structured output self-correction ---


def test_structured_correction_strips_markdown():
    """```json fences stripped before parse."""
    raw = '```json\n{"name": "a", "value": 1}\n```'
    schema = [
        OutputField(name="name", type="str", required=True),
        OutputField(name="value", type="int", required=True),
    ]
    pr = try_parse_structured(raw, schema)
    assert pr.success is True
    assert pr.data == {"name": "a", "value": 1}


def test_structured_correction_includes_error():
    """Retry prompt contains parse error (try_parse_structured returns error in ParseResult)."""
    raw = "not json at all"
    schema = [OutputField(name="x", type="str", required=True)]
    pr = try_parse_structured(raw, schema)
    assert pr.success is False
    assert pr.error is not None
    assert pr.data is None


def test_structured_correction_max_attempts():
    """Exhausted retries raises WorkflowStepError."""
    from hivemind.workflow.runner import _run_step_with_correction
    from hivemind.workflow.context import WorkflowContext

    step = WorkflowStep(
        id="s1",
        task="Return JSON with field x",
        output_schema=[OutputField(name="x", type="str", required=True)],
        retry=1,
    )
    context = WorkflowContext({})
    log = EventLog()
    loop = asyncio.new_event_loop()
    try:
        with patch("hivemind.workflow.runner._run_single_step_sync") as mock_run:
            mock_run.return_value = MagicMock(
                raw_result="not valid json",
                error=None,
                structured=None,
                skipped=False,
                duration_seconds=0.1,
            )
            with pytest.raises(WorkflowStepError) as exc_info:
                loop.run_until_complete(
                    _run_step_with_correction(
                        step,
                        context,
                        "mock",
                        1,
                        None,
                        False,
                        log,
                        loop,
                    )
                )
            assert "failed structured output" in str(exc_info.value)
            assert "2 attempts" in str(exc_info.value) or "attempts" in str(exc_info.value)
    finally:
        loop.close()


def test_format_schema():
    """_format_schema returns readable schema lines."""
    schema = [
        OutputField(name="a", type="str", required=True),
        OutputField(name="b", type="int", required=False),
    ]
    out = _format_schema(schema)
    assert "a" in out
    assert "str" in out
    assert "b" in out
    assert "int" in out


def test_strip_markdown_json():
    """_strip_markdown_json removes ```json and ```."""
    raw = "```json\n{}\n```"
    assert _strip_markdown_json(raw).strip() == "{}"
