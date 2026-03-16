"""Tests for tool analytics."""

import tempfile
from pathlib import Path
from devsper.analytics.tool_analytics import ToolAnalytics


def test_record_and_get_stats():
    """Record tool usage and get stats."""
    with tempfile.TemporaryDirectory() as d:
        a = ToolAnalytics(db_path=Path(d) / "analytics.db")
        a.record("tool_a", True, 10.0)
        a.record("tool_a", False, 20.0)
        a.record("tool_b", True, 5.0)
        stats = a.get_stats()
        assert len(stats) == 2
        by_name = {s["tool_name"]: s for s in stats}
        assert by_name["tool_a"]["count"] == 2
        assert by_name["tool_a"]["success_count"] == 1
        assert by_name["tool_a"]["success_rate"] == 50.0
        assert by_name["tool_b"]["count"] == 1
        assert by_name["tool_b"]["success_rate"] == 100.0
