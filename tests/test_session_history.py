import time
from pathlib import Path
import pytest

from devsper.workspace.session import SessionHistory


@pytest.fixture
def storage_dir(tmp_path):
    d = tmp_path / "project-abc123"
    d.mkdir()
    return d


def test_start_new_session(storage_dir):
    sh = SessionHistory(storage_dir)
    session_id = sh.start_new_session()
    assert len(session_id) == 36  # UUID format
    sessions_dir = storage_dir / "sessions"
    assert sessions_dir.is_dir()


def test_save_and_load_turns(storage_dir):
    sh = SessionHistory(storage_dir)
    session_id = sh.start_new_session()
    sh.save_turn("user", "hello")
    sh.save_turn("assistant", "hi there")
    turns = sh.get_turns(session_id)
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "hello"
    assert turns[1]["role"] == "assistant"


def test_load_last_session(storage_dir):
    sh = SessionHistory(storage_dir)
    sh.start_new_session()
    sh.save_turn("user", "first session")
    time.sleep(0.01)
    sh.start_new_session()
    sh.save_turn("user", "second session")

    sh2 = SessionHistory(storage_dir)
    session_id = sh2.load_last_session()
    turns = sh2.get_turns(session_id)
    assert turns[0]["content"] == "second session"


def test_no_last_session_returns_new(storage_dir):
    sh = SessionHistory(storage_dir)
    session_id = sh.load_last_session()
    assert session_id is not None  # creates new session when none exist


def test_list_sessions(storage_dir):
    sh = SessionHistory(storage_dir)
    sh.start_new_session()
    sh.save_turn("user", "msg1")
    sh.start_new_session()
    sh.save_turn("user", "msg2")
    sessions = sh.list_sessions()
    assert len(sessions) == 2
    # most recent first
    assert sessions[0]["turn_count"] == 1


def test_format_history_for_context(storage_dir):
    sh = SessionHistory(storage_dir)
    sh.start_new_session()
    sh.save_turn("user", "write a function")
    sh.save_turn("assistant", "Here is the function: def foo(): pass")
    text = sh.format_history_for_context(max_turns=10)
    assert "[USER]" in text
    assert "[ASSISTANT]" in text
    assert "write a function" in text
