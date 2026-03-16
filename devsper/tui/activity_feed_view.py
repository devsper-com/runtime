"""
Agent activity feed: chronological feed of agent actions (task started/ended, tool calls).
Reads from EventLog when log path is set.
"""

from textual.widgets import Static


class ActivityFeedView(Static):
    """Shows recent events: TASK_STARTED, TASK_COMPLETED, TOOL_CALLED, etc."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._events_folder: str = ".devsper/events"
        self._log_path: str | None = None
        self._lines: list[str] = []

    def set_events_folder(self, folder: str) -> None:
        self._events_folder = folder

    def set_log_path(self, path: str | None) -> None:
        self._log_path = path

    def refresh_events(self, limit: int = 50) -> None:
        """Load recent events from the event log and display as feed."""
        self._lines = []
        try:
            from pathlib import Path
            import json

            path = self._log_path
            if not path and self._events_folder:
                folder = Path(self._events_folder)
                if folder.is_dir():
                    files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
                    path = str(files[0]) if files else None
            if not path or not Path(path).is_file():
                self._lines = ["(no event log)\nRun swarm to see activity."]
                self.update("\n".join(self._lines))
                return
            with open(path) as f:
                raw_lines = f.readlines()
            for line in raw_lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    ev = obj.get("type", "?")
                    payload = obj.get("payload", {})
                    task_id = payload.get("task_id", "")
                    tool = payload.get("tool", "")
                    if ev == "task_started":
                        self._lines.append(f"[dim]▶ task {task_id}[/dim]")
                    elif ev == "task_completed":
                        self._lines.append(f"[dim]✔ task {task_id}[/dim]")
                    elif ev == "tool_called":
                        self._lines.append(f"[dim]🔧 {tool} (task {task_id})[/dim]")
                    elif ev == "user_injection":
                        msg = (payload.get("message") or "")[:60]
                        if len(payload.get("message") or "") > 60:
                            msg += "…"
                        self._lines.append(f"📌 [bold]User injected:[/] [dim]{msg}[/]")
                    else:
                        self._lines.append(f"[dim]{ev}[/dim]")
                except Exception:
                    self._lines.append(line[:80])
        except Exception as e:
            self._lines = [f"(error: {e})"]
        self.update("\n".join(self._lines[-limit:]))

    def on_mount(self) -> None:
        self.update("(activity feed)\n\nRun swarm to see events.")
