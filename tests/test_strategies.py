"""Tests for strategy-based planning: each strategy returns valid DAG."""

from hivemind.intelligence.strategy_selector import ExecutionStrategy, StrategySelector
from hivemind.intelligence.strategies import get_strategy_for
from hivemind.intelligence.strategies.research_strategy import ResearchStrategy
from hivemind.types.task import Task


def test_research_strategy_returns_four_tasks():
    root = Task(id="root", description="Literature review on diffusion models", dependencies=[])
    strategy = ResearchStrategy()
    tasks = strategy.plan(root)
    assert len(tasks) == 4
    ids = {t.id for t in tasks}
    assert len(ids) == 4
    for t in tasks:
        assert t.description
        assert t.id


def test_research_strategy_dependencies_are_sequential():
    root = Task(id="root", description="Review papers", dependencies=[])
    strategy = ResearchStrategy()
    tasks = strategy.plan(root)
    assert tasks[0].dependencies == []
    for i in range(1, len(tasks)):
        assert len(tasks[i].dependencies) == 1
        assert tasks[i].dependencies[0] == tasks[i - 1].id


def test_selector_chooses_research_for_research_task():
    selector = StrategySelector()
    s = selector.select("Analyze diffusion model research")
    assert s == ExecutionStrategy.RESEARCH


def test_selector_chooses_general_for_neutral_task():
    selector = StrategySelector()
    s = selector.select("Summarize in one sentence.")
    assert s == ExecutionStrategy.GENERAL


def test_get_strategy_for_research():
    strat = get_strategy_for(ExecutionStrategy.RESEARCH)
    assert strat is not None
    tasks = strat.plan(Task(id="r", description="Research topic", dependencies=[]))
    assert len(tasks) >= 1
