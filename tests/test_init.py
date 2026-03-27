"""Tests for devsper init command."""

from pathlib import Path
from unittest.mock import patch

import pytest

from devsper.cli.init import run_init, run_doctor


def test_init_creates_toml(tmp_path):
    """run_init creates devsper.toml (no dataset or example workflow)."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = run_init(interactive=False)
        assert code == 0
        toml = tmp_path / "devsper.toml"
        assert toml.is_file()
        content = toml.read_text()
        assert "[swarm]" in content
        assert "planner = \"auto\"" in content
        assert "worker = \"auto\"" in content
        assert "speculative_execution" in content
        assert (tmp_path / "dataset").is_dir() is False


def test_init_refuses_to_overwrite_toml(tmp_path):
    """run_init does not overwrite existing devsper.toml."""
    (tmp_path / "devsper.toml").write_text("existing")
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = run_init(interactive=False)
        assert code == 1
        assert (tmp_path / "devsper.toml").read_text() == "existing"


def test_doctor_runs_without_error():
    """run_doctor runs and returns 0 or 1 (no exception)."""
    code = run_doctor()
    assert code in (0, 1)


def test_init_writes_ollama_providers_when_ollama_host_env_set(tmp_path, monkeypatch):
    """When OLLAMA_HOST is set, init should enable ollama in devsper.toml."""
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        code = run_init(interactive=False)
        assert code == 0
        content = (tmp_path / "devsper.toml").read_text(encoding="utf-8")
        assert "[providers.ollama]" in content
        assert "enabled = true" in content
        assert 'base_url = "http://localhost:11434"' in content
        assert 'planner = "llama3"' in content
        assert 'worker = "llama3"' in content
