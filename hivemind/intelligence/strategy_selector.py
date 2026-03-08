"""
Strategy selector: choose execution strategy (research, code analysis, data analysis).
"""

import re
from enum import Enum

from hivemind.types.task import Task


class ExecutionStrategy(str, Enum):
    RESEARCH = "research"
    CODE_ANALYSIS = "code_analysis"
    DATA_ANALYSIS = "data_analysis"
    GENERAL = "general"


RESEARCH_KEYWORDS = [
    "research", "paper", "literature", "survey", "cite", "citation",
    "diffusion", "transformer", "methodology", "findings", "review",
]
CODE_KEYWORDS = [
    "code", "codebase", "repository", "refactor", "lint", "test",
    "api", "architecture", "module", "function", "class", "implement",
]
DATA_KEYWORDS = [
    "data", "dataset", "csv", "analysis", "experiment", "metric",
    "statistic", "plot", "visualization", "pipeline", "training",
]


class StrategySelector:
    """
    Select execution strategy from a root task description to tune planner/executor behavior.
    """

    def __init__(self) -> None:
        self._keyword_lists = {
            ExecutionStrategy.RESEARCH: RESEARCH_KEYWORDS,
            ExecutionStrategy.CODE_ANALYSIS: CODE_KEYWORDS,
            ExecutionStrategy.DATA_ANALYSIS: DATA_KEYWORDS,
        }

    def select(self, task: Task | str) -> ExecutionStrategy:
        """
        Return the best strategy for the given task (or task description string).
        """
        text = task.description if isinstance(task, Task) else str(task)
        text = (text or "").lower()
        scores = {s: 0 for s in ExecutionStrategy}
        scores[ExecutionStrategy.GENERAL] = 0
        for strategy, keywords in self._keyword_lists.items():
            for kw in keywords:
                if kw in text:
                    scores[strategy] += 1
        best = max(
            (s for s in ExecutionStrategy if s != ExecutionStrategy.GENERAL),
            key=lambda s: scores[s],
        )
        return best if scores[best] > 0 else ExecutionStrategy.GENERAL

    def suggest_planner_prompt_suffix(self, strategy: ExecutionStrategy) -> str:
        """Return optional prompt suffix to bias the planner for this strategy."""
        if strategy == ExecutionStrategy.RESEARCH:
            return " Focus on: literature search, paper summaries, citation context, methodology comparison."
        if strategy == ExecutionStrategy.CODE_ANALYSIS:
            return " Focus on: structure, dependencies, tests, refactors, documentation."
        if strategy == ExecutionStrategy.DATA_ANALYSIS:
            return " Focus on: data loading, stats, visualizations, experiments, metrics."
        return ""
