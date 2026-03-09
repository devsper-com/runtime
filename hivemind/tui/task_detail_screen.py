"""
Task detail overlay: full description, result, tools, duration, retry count, error.
"""

from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class TaskDetailScreen(ModalScreen[None]):
    """Shows full task details. Receives task dict with task_id, description, result, status, error, role, etc."""

    BINDINGS = [("escape", "dismiss_screen")]

    def __init__(self, task: dict, app_ref: object) -> None:
        super().__init__()
        self._task = task
        self._app_ref = app_ref

    def compose(self) -> ComposeResult:
        t = self._task
        task_id = t.get("task_id", "?")
        desc = (t.get("description") or "(no description)").replace("\n", " ")
        result = (t.get("result") or "(no result)")[:8000]
        status = t.get("status", "?")
        error = t.get("error") or ""
        role = t.get("role") or "—"
        runtime = t.get("runtime") or "—"
        tools_used = t.get("tools_used") or []
        tools_str = ", ".join(tools_used) if tools_used else "—"
        retry = t.get("retry_count", 0)
        lines = [
            f"[bold]Task ID:[/] {task_id}",
            f"[bold]Description:[/] {desc}",
            f"[bold]Role:[/] {role}  [bold]Status:[/] {status}  [bold]Runtime:[/] {runtime}",
            f"[bold]Retry count:[/] {retry}",
            f"[bold]Tools used:[/] {tools_str}",
            "",
            "[bold]Result:[/]",
            result,
        ]
        if error:
            lines.extend(["", "[bold red]Error:[/]", error])
        content = "\n".join(lines)
        with Container(id="task-detail-container"):
            yield ScrollableContainer(Static(content, id="task-detail-content"))
            yield Button("Close", variant="primary", id="task-detail-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "task-detail-close":
            self.dismiss(None)

    def action_dismiss_screen(self) -> None:
        self.dismiss(None)
