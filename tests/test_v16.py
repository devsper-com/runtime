"""Tests for v1.6 Fast Path Execution Engine: semantic cache, complexity router, streaming DAG, parallel tools."""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from hivemind.cache.task_cache import SemanticTaskCache, CacheHit
from hivemind.cache.store import DefaultCacheStore
from hivemind.providers.complexity_router import TaskComplexityRouter, TIERS
from hivemind.types.task import Task, TaskStatus
from hivemind.swarm.scheduler import Scheduler
from hivemind.swarm.executor import Executor
from hivemind.agents.agent import Agent
from hivemind.types.event import events


# ---- Semantic cache ----
def test_semantic_cache_hit_above_threshold(tmp_path: Path) -> None:
    store = DefaultCacheStore(db_path=tmp_path / "cache.db")
    cache = SemanticTaskCache(similarity_threshold=0.92, store=store)
    cache.store_result("Summarize the document", "Summary: short.", "summarize")
    hit = cache.lookup("Summarize the document")
    assert hit is not None
    assert isinstance(hit, CacheHit)
    assert hit.result == "Summary: short."
    assert hit.similarity >= 0.92
    assert "Summarize" in hit.original_description


def test_semantic_cache_miss_below_threshold(tmp_path: Path) -> None:
    store = DefaultCacheStore(db_path=tmp_path / "cache.db")
    cache = SemanticTaskCache(similarity_threshold=0.99, store=store)
    cache.store_result("Summarize the document", "Summary: short.", "summarize")
    hit = cache.lookup("Completely different task: build a rocket")
    assert hit is None


def test_semantic_cache_expiry(tmp_path: Path) -> None:
    import time
    store = DefaultCacheStore(db_path=tmp_path / "cache.db")
    cache = SemanticTaskCache(
        similarity_threshold=0.5,
        store=store,
        max_age_hours=0.0001,
    )
    cache.store_result("Quick task", "Done", "general")
    assert cache.lookup("Quick task") is not None
    time.sleep(1)
    assert cache.lookup("Quick task") is None


def test_semantic_cache_no_false_positives(tmp_path: Path) -> None:
    """At a high threshold, clearly different tasks should not collide."""
    store = DefaultCacheStore(db_path=tmp_path / "cache.db")
    cache = SemanticTaskCache(similarity_threshold=0.99, store=store)
    cache.store_result("Extract key dates from the report", "Dates: 2024-01-01.", "extract")
    hit = cache.lookup("Design a distributed system architecture for high availability")
    assert hit is None


# ---- Complexity router ----
def test_complexity_router_simple_task() -> None:
    router = TaskComplexityRouter()
    task = Task(id="t1", description="Summarize this.", dependencies=[], role="summarize")
    tools: list = []
    tier = router.classify(task, tools)
    assert tier == "simple"


def test_complexity_router_upgrades_for_tools() -> None:
    router = TaskComplexityRouter()
    task = Task(id="t1", description="Analyze data", dependencies=[], role="analysis")
    tools = [object(), object(), object(), object(), object(), object()]
    tier = router.classify(task, tools)
    assert tier == "complex"


# ---- Streaming DAG ----
def test_streaming_dag_unblocks_immediately() -> None:
    """Task B depends on A; B should start as soon as A completes, not wait for C."""
    scheduler = Scheduler()
    completed_order: list[str] = []

    def slow_agent_run(task: Task, model_override: str | None = None) -> str:
        completed_order.append(task.id)
        return "ok"

    agent = Agent(model_name="mock")
    agent.run = slow_agent_run
    a = Task(id="A", description="First", dependencies=[])
    b = Task(id="B", description="Second", dependencies=["A"])
    c = Task(id="C", description="Third", dependencies=[])
    scheduler.add_tasks([a, b, c])
    executor = Executor(
        scheduler=scheduler,
        agent=agent,
        worker_count=2,
        streaming_dag=True,
    )
    asyncio.run(executor.run())
    assert scheduler.is_finished()
    assert "A" in completed_order and "B" in completed_order and "C" in completed_order
    assert completed_order.index("A") < completed_order.index("B")


# ---- Parallel tools ----
def test_parallel_tools_all_called() -> None:
    from unittest.mock import patch
    called: list[str] = []

    def record_tool(name: str, args: dict, task_type: str | None = None) -> str:
        called.append(name)
        return "ok"

    with patch("hivemind.tools.tool_runner.run_tool", record_tool):
        agent = Agent(model_name="mock", use_tools=False, parallel_tools=True)
        tool_calls = [("tool_a", {}), ("tool_b", {}), ("tool_c", {})]
        task = Task(id="x", description="y", dependencies=[])
        results = agent._run_tools_parallel_sync(tool_calls, "general", task)
    assert len(results) == 3
    assert len(called) == 3
    assert "tool_a" in called and "tool_b" in called and "tool_c" in called


def test_parallel_tools_failure_isolation() -> None:
    from unittest.mock import patch

    def fail_second(name: str, args: dict, task_type: str | None = None) -> str:
        if name == "fail":
            raise ValueError("expected failure")
        return "ok"

    with patch("hivemind.tools.tool_runner.run_tool", fail_second):
        agent = Agent(model_name="mock", use_tools=False, parallel_tools=True)
        tool_calls = [("ok1", {}), ("fail", {}), ("ok2", {})]
        task = Task(id="x", description="y", dependencies=[])
        results = agent._run_tools_parallel_sync(tool_calls, "general", task)
    assert len(results) == 3
    assert results[0] == "ok"
    assert "expected failure" in results[1]
    assert results[2] == "ok"
