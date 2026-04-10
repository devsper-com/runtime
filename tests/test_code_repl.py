"""Tests for CodeREPL — slash commands and context building."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devsper.workspace.context import WorkspaceContext
from devsper.workspace.session import SessionHistory
from devsper.workspace.repl import CodeREPL


def _make_workspace(tmp_path: Path, md: str | None = None) -> WorkspaceContext:
    project_id = "abc12345"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    return WorkspaceContext(
        project_root=tmp_path,
        project_id=project_id,
        project_name=tmp_path.name,
        md_content=md,
        storage_dir=storage_dir,
    )


def _make_repl(tmp_path: Path, md: str | None = None) -> CodeREPL:
    ws = _make_workspace(tmp_path, md)
    session = SessionHistory(ws.storage_dir)
    session.start_new_session()
    return CodeREPL(ws, session)


def test_build_task_no_context(tmp_path):
    repl = _make_repl(tmp_path)
    task = repl._build_task("hello")
    assert task == "hello"


def test_build_task_injects_md(tmp_path):
    repl = _make_repl(tmp_path, md="# Project\nDo things.")
    task = repl._build_task("hello")
    assert "<project_instructions>" in task
    assert "Do things." in task
    assert "hello" in task


def test_build_task_injects_history(tmp_path):
    repl = _make_repl(tmp_path)
    repl.session.save_turn("user", "previous question")
    repl.session.save_turn("assistant", "previous answer")
    task = repl._build_task("new question")
    assert "<conversation_history>" in task
    assert "previous question" in task
    assert "new question" in task


def test_handle_slash_exit(tmp_path):
    repl = _make_repl(tmp_path)
    result = repl._handle_slash("/exit")
    assert result is True


def test_handle_slash_new(tmp_path):
    repl = _make_repl(tmp_path)
    old_id = repl.session._session_id
    result = repl._handle_slash("/new")
    assert result is False
    assert repl.session._session_id != old_id


def test_handle_slash_sessions(tmp_path, capsys):
    repl = _make_repl(tmp_path)
    result = repl._handle_slash("/sessions")
    assert result is False  # Should not exit


def test_handle_slash_help(tmp_path, capsys):
    repl = _make_repl(tmp_path)
    result = repl._handle_slash("/help")
    assert result is False


def test_extract_answer_priority(tmp_path):
    repl = _make_repl(tmp_path)
    assert repl._extract_answer({"answer": "hi"}) == "hi"
    assert repl._extract_answer({"result": "res"}) == "res"
    assert repl._extract_answer({"other": "val"}) == "val"
    assert repl._extract_answer({}) == ""
