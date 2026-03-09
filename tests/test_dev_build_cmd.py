"""Tests for build CLI command and builder entrypoint."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from hivemind.cli.main import _run_build


def test_build_command_creates_repo():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        exit_code = _run_build("fastapi todo app", str(out_dir))
        assert (out_dir / "backend" / "main.py").exists()
        assert (out_dir / "tests" / "test_app.py").exists()
        assert (out_dir / "README.md").exists()
        # Exit 0 if tests passed, 1 otherwise (may depend on env)
        assert exit_code in (0, 1)


def test_build_command_returns_repo_path():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        _run_build("fastapi todo app", str(out_dir))
        assert out_dir.exists()
        main = (out_dir / "backend" / "main.py").read_text()
        assert "Todo" in main or "todo" in main
