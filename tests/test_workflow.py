"""Tests for workflow loader and runner."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from hivemind.workflow.loader import load_workflow
from hivemind.workflow.runner import run_workflow


def test_run_workflow_sequential():
    """Workflow steps run in order (dependencies)."""
    steps = ["Step one", "Step two"]
    with patch("hivemind.agents.agent.generate", side_effect=["out1", "out2"]):
        results = run_workflow(steps, worker_model="mock", worker_count=1)
    assert len(results) == 2
    assert "out1" in results.values()
    assert "out2" in results.values()


def test_load_workflow_from_path():
    """Load workflow from a TOML file path."""
    with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
        f.write(b'[workflow]\nname = "test_wf"\nsteps = ["a", "b"]\n')
        path = Path(f.name)
    try:
        wf = load_workflow("test_wf", config_path=path)
        assert wf is not None
        assert wf["name"] == "test_wf"
        assert wf["steps"] == ["a", "b"]
    finally:
        path.unlink(missing_ok=True)


def test_list_workflows_empty_without_file():
    """Without a workflow file, list_workflows returns [] when we use a path that doesn't exist."""
    wf = load_workflow("nonexistent", config_path=Path("/nonexistent/hivemind.toml"))
    assert wf is None
