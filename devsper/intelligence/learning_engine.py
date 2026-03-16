"""
Learning engine: analyze previous swarm runs (telemetry + memory) to improve planning.

Detects: which tasks fail, slow tools, patterns. Can adjust planner prompts or suggest optimizations.
"""

import os
from pathlib import Path

from devsper.runtime.telemetry import collect_telemetry
from devsper.memory.memory_store import get_default_store
from devsper.memory.memory_types import MemoryType


class LearningEngine:
    """
    Analyze past runs via telemetry and memory to suggest improvements:
    failing tasks, slow tools, planner prompt adjustments.
    """

    def __init__(self, events_folder: str = ".devsper/events", memory_store=None) -> None:
        self.events_folder = events_folder
        self.memory_store = memory_store or get_default_store()

    def analyze_telemetry(self, log_path: str | None = None) -> dict:
        """
        Collect telemetry from an event log. If log_path is None, use latest from events_folder.
        Returns dict with tasks_completed, tasks_failed, avg_task_duration_seconds, etc.
        """
        if log_path is None:
            log_path = self._latest_log_path()
        if not log_path or not os.path.exists(log_path):
            return {
                "tasks_completed": 0,
                "tasks_failed": 0,
                "avg_task_duration_seconds": 0.0,
                "avg_agent_latency_seconds": 0.0,
                "max_concurrency": 0,
                "task_success_rate": 0.0,
            }
        return collect_telemetry(log_path)

    def _latest_log_path(self) -> str | None:
        """Return path to most recent events jsonl in events_folder."""
        if not os.path.isdir(self.events_folder):
            return None
        files = list(Path(self.events_folder).glob("events_*.jsonl"))
        if not files:
            return None
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(files[0])

    def get_failure_patterns(self, log_path: str | None = None) -> list[str]:
        """
        Return list of suggested failure patterns (e.g. "high failure rate", "slow tasks").
        """
        tele = self.analyze_telemetry(log_path)
        patterns = []
        if tele.get("tasks_failed", 0) > 0 and tele.get("task_success_rate", 1) < 0.8:
            patterns.append("high_failure_rate")
        if tele.get("avg_task_duration_seconds", 0) > 60:
            patterns.append("slow_tasks")
        if tele.get("avg_agent_latency_seconds", 0) > 30:
            patterns.append("slow_agent_latency")
        return patterns

    def get_planner_suggestions(self, log_path: str | None = None) -> str:
        """
        Return a string of suggestions to add to planner context (e.g. "Avoid very long tasks").
        """
        patterns = self.get_failure_patterns(log_path)
        if not patterns:
            return ""
        suggestions = []
        if "high_failure_rate" in patterns:
            suggestions.append("Consider breaking tasks into smaller steps to reduce failures.")
        if "slow_tasks" in patterns:
            suggestions.append("Previous runs had long-running tasks; consider shorter subtasks.")
        if "slow_agent_latency" in patterns:
            suggestions.append("Agent latency was high; consider fewer tool-heavy steps.")
        return " ".join(suggestions)

    def summarize_memory_for_learning(self, limit: int = 50) -> dict[str, int]:
        """
        Summarize stored memory by type (for learning dashboard).
        """
        records = self.memory_store.list_memory(limit=limit)
        by_type: dict[str, int] = {}
        for r in records:
            k = r.memory_type.value
            by_type[k] = by_type.get(k, 0) + 1
        return by_type
