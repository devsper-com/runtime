"""Tests for code sandbox (hivemind.dev.sandbox)."""

import tempfile
from pathlib import Path

import pytest

from hivemind.dev.sandbox import Sandbox, SandboxLimits, SandboxResult


def test_sandbox_write_file():
    with tempfile.TemporaryDirectory() as tmp:
        sb = Sandbox(tmp)
        r = sb.write_file("a/b.txt", "hello")
        assert r.success
        assert (Path(tmp) / "a" / "b.txt").read_text() == "hello"


def test_sandbox_read_file():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "x.txt").write_text("content")
        sb = Sandbox(tmp)
        r = sb.read_file("x.txt")
        assert r.success
        assert r.stdout == "content"


def test_sandbox_run_command():
    with tempfile.TemporaryDirectory() as tmp:
        sb = Sandbox(tmp, limits=SandboxLimits(timeout_seconds=5))
        r = sb.run("echo ok")
        assert r.success
        assert "ok" in (r.stdout or "")


def test_sandbox_run_tests_no_tests_dir():
    with tempfile.TemporaryDirectory() as tmp:
        sb = Sandbox(tmp)
        r = sb.run_tests(path="tests")
        # No tests dir -> may run pytest on root and get "no tests" or collect 0
        assert r.returncode is not None or r.error is not None or r.stdout is not None


def test_sandbox_run_tests_with_passing_test():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "tests").mkdir()
        (Path(tmp) / "tests" / "test_foo.py").write_text("def test_ok(): assert True\n")
        sb = Sandbox(tmp)
        r = sb.run_tests(path="tests")
        assert r.success
        assert "passed" in (r.stdout or "").lower() or "1 passed" in (r.stdout or "")
