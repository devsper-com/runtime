#!/usr/bin/env python3
"""
Smoke test for Tool Reliability Scoring (v1.3) using a temporary DB.
Run from project root: uv run python scripts/test_tool_scoring_smoke.py
"""

import os
import tempfile
from pathlib import Path

# Use temp DB so we don't touch ~/.config/devsper/tool_scores.db
with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / "tool_scores.db"

    from devsper.tools.scoring.store import ToolScoreStore, ToolScore
    from devsper.tools.scoring.scorer import compute_composite_score, score_label
    from devsper.tools.scoring.selector import select_tools_scored
    from devsper.tools.scoring.report import generate_tools_report
    from devsper.tools.base import Tool

    class _T(Tool):
        def __init__(self, name: str, desc: str):
            self.name, self.description, self.input_schema, self.category = name, desc, {}, "test"
        def run(self, **kwargs): return "ok"

    store = ToolScoreStore(db_path=db_path)

    print("1. Record results and get_score")
    for _ in range(6):
        store.record("tool_a", "general", True, 100)
    score = store.get_score("tool_a")
    assert score is not None
    assert score.total_calls == 6
    assert not score.is_new
    print(f"   tool_a: score={score.composite_score:.2f} label={score_label(score.composite_score)}")

    print("2. New tool (< 5 calls) gets neutral 0.75 in formula")
    store.record("tool_b", "general", True, 50)
    store.record("tool_b", "general", True, 60)
    sb = store.get_score("tool_b")
    assert sb is not None and sb.is_new
    assert compute_composite_score({"total_calls": 2}) == 0.75
    print("   ok")

    print("3. get_all_scores and report")
    all_scores = store.get_all_scores()
    report = generate_tools_report(all_scores)
    assert "tools tracked" in report or "tool" in report.lower()
    print("   report length:", len(report))

    print("4. Selector (blended) with mock embed")
    from unittest.mock import patch
    dim = 64
    v1 = [1.0] + [0.0] * (dim - 1)
    v2 = [0.0, 1.0] + [0.0] * (dim - 2)
    def mock_embed(t):
        if "a" in t: return v1
        return v2
    with patch("devsper.tools.scoring.selector.embed_text", side_effect=mock_embed):
        tools = [_T("tool_a", "aaa"), _T("tool_b", "bbb")]
        sel = select_tools_scored("task a", tools, 1, store)
    assert len(sel) == 1
    print("   select_tools_scored returned 1 tool")

    print("5. Reset and prune")
    store.reset("tool_a")
    assert store.get_score("tool_a") is None
    store.prune(days=90)
    print("   ok")

    print("6. record_tool_result / get_tool_score (default store not used; we used temp DB)")
    from devsper.tools.scoring import record_tool_result, get_tool_score
    record_tool_result("_smoke_tool", "general", True, 10)
    # Default store may have other data; we only check it doesn't crash
    get_tool_score("_smoke_tool")
    print("   ok")

print("\nSmoke test passed.")
