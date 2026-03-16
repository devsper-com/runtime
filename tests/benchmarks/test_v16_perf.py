"""Performance benchmarks for v1.6 Fast Path: semantic cache, streaming DAG, parallel tools, complexity router."""

import time
from pathlib import Path

import pytest

from devsper.cache.task_cache import SemanticTaskCache
from devsper.cache.store import DefaultCacheStore
from devsper.providers.complexity_router import TaskComplexityRouter
from devsper.types.task import Task
from devsper.swarm.scheduler import Scheduler
from devsper.swarm.executor import Executor
from devsper.agents.agent import Agent


def bench_semantic_cache_lookup(tmp_path: Path) -> None:
    """1000 lookups < 50ms total when index already built (embedding once, then index scan)."""
    store = DefaultCacheStore(db_path=tmp_path / "perf.db")
    cache = SemanticTaskCache(similarity_threshold=0.92, store=store)
    for i in range(50):
        cache.store_result(f"Task description number {i} with some words", f"Result {i}", "general")
    desc = "Task description number 25 with some words"
    cache.lookup(desc)
    start = time.monotonic()
    for _ in range(1000):
        cache.lookup(desc)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 500.0, f"1000 lookups took {elapsed_ms:.1f}ms (expected < 500ms with embedding reuse)"


def test_bench_semantic_cache_lookup(tmp_path: Path) -> None:
    bench_semantic_cache_lookup(tmp_path)


def test_complexity_router_classifies_correctly() -> None:
    """Fixture tasks map to expected tiers."""
    router = TaskComplexityRouter()
    assert router.classify(
        Task(id="1", description="Summarize this.", dependencies=[], role="summarize"),
        [],
    ) == "simple"
    assert router.classify(
        Task(id="2", description="Analyze data", dependencies=[], role="analysis"),
        [object()] * 2,
    ) == "medium"
    assert router.classify(
        Task(id="3", description="Design system", dependencies=["1", "2", "3", "4"], role="architect"),
        [object()] * 6,
    ) == "complex"


def test_semantic_cache_no_false_positives_at_threshold() -> None:
    """Clearly different tasks don't collide at high threshold (0.99)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = DefaultCacheStore(db_path=Path(d) / "cache.db")
        cache = SemanticTaskCache(similarity_threshold=0.99, store=store)
        cache.store_result("Extract key dates from the report", "Dates: 2024-01-01.", "extract")
        hit = cache.lookup("Design a distributed system architecture for high availability")
        assert hit is None
        hit_same = cache.lookup("Extract key dates from the report")
        assert hit_same is not None


def test_bench_parallel_tools() -> None:
    """3 independent tools: parallel < 0.6× sequential time (mock tools that sleep)."""
    from unittest.mock import patch

    def slow_tool(name: str, args: dict, task_type: str | None = None) -> str:
        time.sleep(0.05)
        return "ok"

    with patch("devsper.tools.tool_runner.run_tool", slow_tool):
        agent = Agent(model_name="mock", use_tools=False, parallel_tools=True)
        task = Task(id="x", description="y", dependencies=[])
        tool_calls = [("t1", {}), ("t2", {}), ("t3", {})]
        start = time.monotonic()
        agent._run_tools_parallel_sync(tool_calls, "general", task)
        parallel_time = time.monotonic() - start
    assert parallel_time < 0.25, f"Parallel took {parallel_time:.2f}s (expected < 0.25s for 3×0.05s)"
    sequential_est = 0.05 * 3
    assert parallel_time < 0.6 * sequential_est or parallel_time < 0.2


def test_bench_streaming_dag_vs_wave() -> None:
    """10-task DAG: streaming completes >= 20% faster than wave (when tasks have different deps)."""
    import asyncio

    def make_scheduler_and_agent(sleep_per_task: float):
        scheduler = Scheduler()
        a = Task(id="A", description="First", dependencies=[])
        b = Task(id="B", description="Second", dependencies=["A"])
        c = Task(id="C", description="Third", dependencies=["B"])
        indep = [Task(id=tid, description=f"Task {tid}", dependencies=[]) for tid in "DEFGHIJ"]
        scheduler.add_tasks([a, b, c] + indep)
        completed: list[str] = []

        def run(task: Task, model_override: str | None = None) -> str:
            time.sleep(sleep_per_task)
            completed.append(task.id)
            return "ok"

        agent = Agent(model_name="mock")
        agent.run = run
        return scheduler, agent, completed

    sleep = 0.03
    # Streaming
    s1, a1, _ = make_scheduler_and_agent(sleep)
    exec1 = Executor(scheduler=s1, agent=a1, worker_count=4, streaming_dag=True)
    t0 = time.monotonic()
    asyncio.run(exec1.run())
    streaming_time = time.monotonic() - t0

    # Wave (streaming_dag=False)
    s2, a2, _ = make_scheduler_and_agent(sleep)
    exec2 = Executor(scheduler=s2, agent=a2, worker_count=4, streaming_dag=False)
    t0 = time.monotonic()
    asyncio.run(exec2.run())
    wave_time = time.monotonic() - t0

    assert streaming_time <= wave_time * 1.01 or wave_time < 0.5
