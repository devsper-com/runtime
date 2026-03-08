"""
Logs panel: stream events from EventLog.

Polls event log file(s) or uses in-memory events. Displays event type and payload summary.
"""

import os
from pathlib import Path

from textual.widgets import Static


class LogsView(Static):
    """Displays event log stream: event type, task_id, etc."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._log_path: str | None = None
        self._events_folder: str = ".hivemind/events"
        self._max_lines: int = 100
        self._last_count: int = 0

    def set_log_path(self, path: str | None) -> None:
        """Set the event log file path to read from."""
        self._log_path = path

    def set_events_folder(self, folder: str) -> None:
        """Set folder to search for latest events_*.jsonl."""
        self._events_folder = folder

    def _latest_log_path(self) -> str | None:
        if self._log_path and os.path.exists(self._log_path):
            return self._log_path
        if not os.path.isdir(self._events_folder):
            alt = ".hivemind/events"
            if os.path.isdir(alt):
                self._events_folder = alt
            else:
                return None
        files = list(Path(self._events_folder).glob("events_*.jsonl"))
        if not files:
            return None
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return str(files[0])

    def _read_events(self) -> list[str]:
        """Read events and return list of display lines."""
        path = self._latest_log_path()
        if not path:
            return [
                "No logs yet.",
                "",
                "↑ Run a task (prompt above, then Enter or r);",
                "  events will appear here.",
            ]
        lines = []
        try:
            from hivemind.types.event import Event

            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = Event.model_validate_json(line)
                        payload = ev.payload or {}
                        task_id = payload.get("task_id", "")
                        extra = f" {task_id}" if task_id else ""
                        lines.append(f"{ev.type.value}{extra}")
                    except Exception:
                        lines.append(line[:80])
        except Exception as e:
            lines.append(f"(error: {e})")
        return lines[-self._max_lines :] if len(lines) > self._max_lines else lines

    def refresh_logs(self) -> None:
        """Re-read event log and update display."""
        lines = self._read_events()
        self.update("\n".join(lines) if lines else "(no events)")

    def on_mount(self) -> None:
        self.refresh_logs()
