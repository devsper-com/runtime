"""Tests for tool reliability scoring (store, scorer, selector, env bypass)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from hivemind.tools.base import Tool
from hivemind.tools.scoring.scorer import compute_composite_score, score_label
from hivemind.tools.scoring.store import ToolScoreStore, ToolScore
from hivemind.tools.scoring.selector import select_tools_scored


# ---- Scorer ----

def test_composite_score_new_tool():
    """< 5 calls returns 0.75."""
    assert compute_composite_score({"total_calls": 0}) == 0.75
    assert compute_composite_score({"total_calls": 3}) == 0.75
    assert compute_composite_score({"total_calls": 4}) == 0.75


def test_composite_score_reliable():
    """100% success, low latency -> >= 0.85."""
    score = compute_composite_score({
        "success_rate": 1.0,
        "avg_latency_ms": 100.0,
        "total_calls": 20,
        "recent_failures": 0,
    })
    assert score >= 0.85


def test_composite_score_dead():
    """0% success, 10+ calls -> ~0.05."""
    score = compute_composite_score({
        "success_rate": 0.0,
        "avg_latency_ms": 5000.0,
        "total_calls": 15,
        "recent_failures": 15,
    })
    assert 0.04 <= score <= 0.06


def test_score_label():
    assert score_label(0.90) == "excellent"
    assert score_label(0.85) == "excellent"
    assert score_label(0.70) == "good"
    assert score_label(0.65) == "good"
    assert score_label(0.50) == "degraded"
    assert score_label(0.40) == "degraded"
    assert score_label(0.30) == "poor"
    assert score_label(0.05) == "poor"


# ---- Store ----

def test_store_record_and_retrieve():
    """Round-trip through SQLite."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "scores.db"
        store = ToolScoreStore(db_path=path)
        store.record("tool_a", "general", success=True, latency_ms=50)
        store.record("tool_a", "general", success=True, latency_ms=60)
        store.record("tool_a", "general", success=False, latency_ms=10)
        score = store.get_score("tool_a")
        assert score is not None
        assert score.tool_name == "tool_a"
        assert score.total_calls == 3
        assert score.success_rate == pytest.approx(2 / 3)
        assert score.composite_score >= 0.05
        assert score.composite_score <= 1.0
        assert store.get_score("nonexistent") is None


def test_store_prune():
    """Records older than 90 days are removed."""
    from datetime import datetime, timezone, timedelta

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "scores.db"
        store = ToolScoreStore(db_path=path)
        store.record("t1", "general", True, 10)
        assert store.result_count() >= 1
        # Manually insert an old record
        old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        with store._conn() as c:
            c.execute(
                "INSERT INTO tool_results (tool_name, task_type, success, latency_ms, timestamp) VALUES (?, ?, ?, ?, ?)",
                ("t_old", "general", 1, 5, old_ts),
            )
        n_before = store.result_count()
        deleted = store.prune(days=90)
        assert deleted >= 1
        # t_old should be gone; t1 might still be there
        with store._conn() as c:
            rows = c.execute("SELECT tool_name FROM tool_results").fetchall()
        names = [r[0] for r in rows]
        assert "t_old" not in names


def test_store_reset():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "scores.db"
        store = ToolScoreStore(db_path=path)
        store.record("x", "general", True, 1)
        assert store.get_score("x") is not None
        store.reset("x")
        assert store.get_score("x") is None


# ---- Selector ----

class _StubTool(Tool):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.input_schema = {}
        self.category = "test"

    def run(self, **kwargs) -> str:
        return "ok"


def test_selector_prefers_reliable():
    """Two equally similar tools; higher-scored one wins when scoring enabled."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "scores.db"
        store = ToolScoreStore(db_path=path)
        # Tool A: many successes
        for _ in range(15):
            store.record("tool_a", "general", success=True, latency_ms=50)
        # Tool B: same description (similar) but poor score
        for _ in range(15):
            store.record("tool_b", "general", success=False, latency_ms=5000)
        a = _StubTool("tool_a", "run a task")
        b = _StubTool("tool_b", "run a task")  # same description -> same similarity
        tools = [a, b]
        selected = select_tools_scored("run a task", tools, 1, store)
        assert len(selected) == 1
        assert selected[0].name == "tool_a"


def test_selector_similarity_still_dominates():
    """When similarity is 1.0 for one tool and 0 for the other, similarity (70%) dominates reliability (30%)."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "scores.db"
        store = ToolScoreStore(db_path=path)
        # Degraded tool (will get sim=1 via mock)
        for _ in range(15):
            store.record("relevant", "general", success=True, latency_ms=5000)
        for _ in range(5):
            store.record("relevant", "general", success=False, latency_ms=100)
        # Reliable tool (will get sim=0 via mock)
        for _ in range(20):
            store.record("reliable", "general", success=True, latency_ms=10)
        relevant = _StubTool("relevant", "search papers")
        reliable = _StubTool("reliable", "format code")
        tools = [relevant, reliable]
        # Mock: task embeds to [1,0,...], relevant to [1,0,...], reliable to [0,1,...] -> sim 1 and 0
        dim = 64
        task_vec = [1.0] + [0.0] * (dim - 1)
        rel_vec = [1.0] + [0.0] * (dim - 1)
        irr_vec = [0.0, 1.0] + [0.0] * (dim - 2)
        call_count = [0]

        def mock_embed(text):
            call_count[0] += 1
            if "relevant" in text or "search" in text:
                return rel_vec
            if "reliable" in text or "format" in text:
                return irr_vec
            return task_vec

        with patch("hivemind.tools.scoring.selector.embed_text", side_effect=mock_embed):
            selected = select_tools_scored("search papers", tools, 1, store)
        assert len(selected) == 1
        # 0.7*1 + 0.3*degraded > 0.7*0 + 0.3*excellent => relevant wins
        assert selected[0].name == "relevant"


def test_env_bypass():
    """HIVEMIND_DISABLE_TOOL_SCORING=1 returns similarity-only ranking."""
    os.environ["HIVEMIND_DISABLE_TOOL_SCORING"] = "1"
    try:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "scores.db"
            store = ToolScoreStore(db_path=path)
            # Make tool_b have better score but tool_a more relevant to task
            for _ in range(20):
                store.record("tool_b", "general", success=True, latency_ms=1)
            for _ in range(20):
                store.record("tool_a", "general", success=False, latency_ms=10000)
            a = _StubTool("tool_a", "search papers and citations")
            b = _StubTool("tool_b", "unrelated utility")
            tools = [a, b]
            selected = select_tools_scored("search papers", tools, 1, store)
            assert len(selected) == 1
            # With scoring disabled, similarity only -> tool_a should win (matches "search papers")
            assert selected[0].name == "tool_a"
    finally:
        os.environ.pop("HIVEMIND_DISABLE_TOOL_SCORING", None)
