"""
Overlay screen: inject a note to the swarm (stored as high-priority memory).
"""

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from devsper.types.event import Event, events
from devsper.memory.memory_store import get_default_store, generate_memory_id
from devsper.memory.memory_types import MemoryRecord, MemoryType


class InjectScreen(ModalScreen[None]):
    """Modal: 'Inject note to swarm' input; on Submit store as episodic + user_injection and close."""

    BINDINGS = [("escape", "cancel")]

    def compose(self) -> ComposeResult:
        with Container(id="inject-container"):
            yield Static("Inject note to swarm:", id="inject-label")
            yield Input(placeholder="Type your message...", id="inject-input")
            with Container(id="inject-buttons"):
                yield Button("Submit", variant="primary", id="inject-submit")
                yield Button("Cancel", id="inject-cancel")

    def on_mount(self) -> None:
        self.query_one("#inject-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "inject-submit":
            self._submit()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "inject-input":
            self._submit()

    def _submit(self) -> None:
        inp = self.query_one("#inject-input", Input)
        message = (inp.value or "").strip()
        if not message:
            return
        store = get_default_store()
        record = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.EPISODIC,
            source_task="user_injection",
            content=message,
            tags=["user_injection"],
        )
        store.store(record)
        log_path = getattr(self.app, "_event_log_path", None)
        if log_path:
            try:
                ev = Event(
                    timestamp=datetime.now(timezone.utc),
                    type=events.USER_INJECTION,
                    payload={"message": message[:500]},
                )
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(ev.model_dump_json() + "\n")
            except OSError:
                pass
        self.dismiss(None)
        self.notify("📌 Injected. Subsequent agent calls will see this note.", severity="information")

    def action_cancel(self) -> None:
        self.dismiss(None)
