import io
from unittest.mock import MagicMock, patch

import pytest

from devsper.workspace.display import CallbackEventLog, ToolCallDisplay, format_event_line


def test_format_event_line_tool_start():
    line = format_event_line({"type": "tool_start", "tool": "read_file", "args": {"file": "foo.py"}})
    assert "read_file" in line or "foo.py" in line


def test_format_event_line_tool_done():
    line = format_event_line({"type": "tool_done", "tool": "read_file", "result": {"lines": 42}})
    assert line is not None


def test_format_event_line_agent_start():
    line = format_event_line({"type": "agent_start", "role": "code", "description": "Write tests"})
    assert line is not None


def test_format_event_line_unknown_returns_none():
    line = format_event_line({"type": "swarm_heartbeat"})
    assert line is None


def test_callback_event_log_calls_callback():
    received = []
    cel = CallbackEventLog(callback=received.append, events_folder_path="/tmp/devsper-test-events")

    mock_event = MagicMock()
    mock_event.type = "TASK_STARTED"
    type(mock_event).model_dump = MagicMock(return_value={"type": "TASK_STARTED", "payload": {}})

    cel.append_event(mock_event)
    assert len(received) == 1
