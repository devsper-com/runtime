"""Strategy-based planning: map ExecutionStrategy to DAG-producing strategies."""

from hivemind.intelligence.strategy_selector import ExecutionStrategy
from hivemind.intelligence.strategies.base import Strategy
from hivemind.intelligence.strategies.code_analysis_strategy import CodeAnalysisStrategy
from hivemind.intelligence.strategies.data_science_strategy import DataScienceStrategy
from hivemind.intelligence.strategies.document_pipeline_strategy import DocumentPipelineStrategy
from hivemind.intelligence.strategies.experiment_strategy import ExperimentStrategy
from hivemind.intelligence.strategies.research_strategy import ResearchStrategy

STRATEGY_REGISTRY: dict[ExecutionStrategy, type[Strategy]] = {
    ExecutionStrategy.RESEARCH: ResearchStrategy,
    ExecutionStrategy.CODE_ANALYSIS: CodeAnalysisStrategy,
    ExecutionStrategy.DATA_ANALYSIS: DataScienceStrategy,
    ExecutionStrategy.DOCUMENT: DocumentPipelineStrategy,
    ExecutionStrategy.EXPERIMENT: ExperimentStrategy,
}


def get_strategy_for(strategy_enum: ExecutionStrategy) -> Strategy | None:
    """Return a strategy instance for the given enum, or None for GENERAL."""
    cls = STRATEGY_REGISTRY.get(strategy_enum)
    return cls() if cls else None
