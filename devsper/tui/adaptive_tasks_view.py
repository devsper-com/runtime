"""
Adaptive task creation: show when alternative tasks were injected (e.g. after failure).
"""

from textual.widgets import Static


class AdaptiveTasksView(Static):
    """Shows adaptive events: failed tasks and newly created alternative tasks."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._events_folder: str = ".devsper/events"
        self._log_path: str | None = None

    def set_events_folder(self, folder: str) -> None:
        self._events_folder = folder

    def set_log_path(self, path: str | None) -> None:
        self._log_path = path

    def refresh_adaptive_events(self, limit: int = 20) -> None:
        """Load task_failed and subsequent task_created from event log."""
        lines = ["(Adaptive task creation)", ""]
        try:
            from pathlib import Path
            import json

            path = self._log_path
            if not path and self._events_folder:
                folder = Path(self._events_folder)
                if folder.is_dir():
                    files = sorted(
                        folder.glob("*.jsonl"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    path = str(files[0]) if files else None
            if not path or not Path(path).is_file():
                self.update("(Adaptive tasks)\n\nNo event log.\nRun with adaptive_execution=true to see alternatives.")
                return
            with open(path) as f:
                raw = f.readlines()
            failed_ids = set()
            created_after_fail = []
            for line in raw:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    ev = obj.get("type", "?")
                    payload = obj.get("payload", {})
                    if ev == "task_failed":
                        failed_ids.add(payload.get("task_id", ""))
                    if ev == "task_created" and failed_ids:
                        created_after_fail.append(
                            (payload.get("task_id", ""), payload.get("description", "")[:60])
                        )
                except Exception:
                    pass
            if failed_ids:
                lines.append("Failed tasks:")
                for tid in list(failed_ids)[:5]:
                    lines.append(f"  • {tid}")
                lines.append("")
            if created_after_fail:
                lines.append("New tasks (after failure):")
                for tid, desc in created_after_fail[-limit:]:
                    lines.append(f"  • {tid}: {desc}")
            elif not failed_ids:
                lines.append("No adaptive events in this run.")
        except Exception as e:
            lines.append(f"Error: {e}")
        self.update("\n".join(lines))
