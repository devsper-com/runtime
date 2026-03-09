"""Tests for debug loop (hivemind.dev.debugger)."""

import tempfile
from pathlib import Path

import pytest

from hivemind.dev.sandbox import Sandbox
from hivemind.dev.debugger import debug_loop, DebugResult


def test_debug_loop_passes_when_tests_pass():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "tests").mkdir()
        (Path(tmp) / "tests" / "test_ok.py").write_text("def test_ok(): assert True\n")
        sb = Sandbox(tmp)
        result = debug_loop(sb, max_iterations=2, get_fix=None)
    assert result.passed
    assert result.iterations >= 1


def test_debug_loop_fails_when_tests_fail_and_no_fix():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "tests").mkdir()
        (Path(tmp) / "tests" / "test_fail.py").write_text("def test_fail(): assert False\n")
        sb = Sandbox(tmp)
        result = debug_loop(sb, max_iterations=2, get_fix=None)
    assert not result.passed
    assert result.iterations <= 2
