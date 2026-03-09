"""
Run analysis: build RunReport from events, cost estimation, LLM analysis, Rich formatting.
"""

from hivemind.intelligence.analysis.run_report import (
    RunReport,
    TaskSummary,
    build_report_from_events,
)
from hivemind.intelligence.analysis.analyzer import analyze
from hivemind.intelligence.analysis.formatter import print_run_report

__all__ = [
    "RunReport",
    "TaskSummary",
    "build_report_from_events",
    "analyze",
    "print_run_report",
]
