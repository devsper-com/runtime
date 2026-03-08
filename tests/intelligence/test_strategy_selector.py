"""Tests for strategy selector."""
import pytest

from hivemind.types.task import Task
from hivemind.intelligence.strategy_selector import StrategySelector, ExecutionStrategy


def test_select_research():
    sel = StrategySelector()
    t = Task(id="r", description="Review research papers on diffusion models", dependencies=[])
    assert sel.select(t) == ExecutionStrategy.RESEARCH


def test_select_code_analysis():
    sel = StrategySelector()
    t = Task(id="c", description="Analyze the codebase and refactor", dependencies=[])
    assert sel.select(t) == ExecutionStrategy.CODE_ANALYSIS


def test_select_data_analysis():
    sel = StrategySelector()
    t = Task(id="d", description="Run data analysis and plot metrics", dependencies=[])
    assert sel.select(t) == ExecutionStrategy.DATA_ANALYSIS


def test_select_general():
    sel = StrategySelector()
    t = Task(id="g", description="Do something generic", dependencies=[])
    assert sel.select(t) == ExecutionStrategy.GENERAL


def test_suggest_planner_prompt_suffix():
    sel = StrategySelector()
    s = sel.suggest_planner_prompt_suffix(ExecutionStrategy.RESEARCH)
    assert "literature" in s or "research" in s
