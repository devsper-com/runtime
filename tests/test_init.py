"""Tests for hivemind init command."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hivemind.cli.init import run_init, run_doctor


def test_init_creates_toml_and_dataset(tmp_path):
    """run_init creates hivemind.toml and dataset folder when they don't exist."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = run_init(interactive=False)
        assert code == 0
        toml = tmp_path / "hivemind.toml"
        assert toml.is_file()
        content = toml.read_text()
        assert "[swarm]" in content
        assert "planner = \"auto\"" in content
        assert "worker = \"auto\"" in content
        assert "[workflow.example]" in content or "workflow" in content
        dataset = tmp_path / "dataset"
        assert dataset.is_dir()


def test_init_refuses_to_overwrite_toml(tmp_path):
    """run_init does not overwrite existing hivemind.toml."""
    (tmp_path / "hivemind.toml").write_text("existing")
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = run_init(interactive=False)
        assert code == 1
        assert (tmp_path / "hivemind.toml").read_text() == "existing"


def test_doctor_runs_without_error():
    """run_doctor runs and returns 0 or 1 (no exception)."""
    code = run_doctor()
    assert code in (0, 1)
