"""
TUI layout: output-first. One main view = prompt + full-height output.

No side panels on main screen (no scrolling in tiny boxes). Dashboard (d) for tasks/logs/memory.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Input, Static

from hivemind.tui.results_view import ResultsView


class PromptInput(Input):
    """Input that yields focus on Escape so r / d / q work."""

    def on_key(self, event):
        if event.key == "escape":
            try:
                self.app.set_focus(self.app.query_one("#results-view"))
            except Exception:
                pass
            event.prevent_default().stop()


class HivemindLayout(Static):
    """Main view: compact branding → prompt → one large Output (rest of screen)."""

    def compose(self) -> ComposeResult:
        with Container(id="branding"):
            yield Static("Hivemind — Distributed AI Swarm Runtime", id="logo-line")
        with Container(id="prompt-box"):
            yield PromptInput(
                placeholder="Ask anything... e.g. Summarize swarm intelligence in one paragraph.",
                id="prompt-input",
            )
        yield Static(
            "Esc unfocus input  •  Enter or r run  •  o output  •  q quit",
            id="action-hints",
        )
        with Vertical(id="output-container"):
            yield Static("Response", classes="output-title")
            yield ResultsView(id="results-view")
