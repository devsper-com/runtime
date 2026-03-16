"""Tests for DAG export (Mermaid, Graphviz)."""

import json
import tempfile
from pathlib import Path
from devsper.visualization.dag_export import (
    load_dag,
    export_mermaid,
    export_graphviz,
    list_run_ids,
)


def test_export_mermaid():
    """Mermaid output contains flowchart and nodes."""
    nodes = [{"id": "a", "description": "Task A"}, {"id": "b", "description": "Task B"}]
    edges = [("a", "b")]
    out = export_mermaid(nodes, edges)
    assert "flowchart" in out
    assert "a" in out
    assert "b" in out
    assert "Task A" in out or "Task_B" in out
    assert "-->" in out


def test_export_graphviz():
    """Graphviz output contains digraph and edges."""
    nodes = [{"id": "a", "description": "Task A"}]
    edges = [("a", "b")]
    out = export_graphviz(nodes, edges)
    assert "digraph" in out
    assert "->" in out


def test_load_dag():
    """Load DAG from JSON file."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "run1_dag.json"
        path.write_text(
            json.dumps(
                {
                    "nodes": [{"id": "x", "description": "X"}],
                    "edges": [["x", "y"]],
                }
            )
        )
        nodes, edges = load_dag(d, "run1")
        assert len(nodes) == 1
        assert nodes[0]["id"] == "x"
        assert edges == [("x", "y")]


def test_list_run_ids():
    """list_run_ids returns run ids from _dag.json files."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "events_123_dag.json").write_text("{}")
        (Path(d) / "events_456_dag.json").write_text("{}")
        ids = list_run_ids(d)
        assert "events_123" in ids
        assert "events_456" in ids
