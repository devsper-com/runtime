"""Devsper TUI — live workflow execution viewer."""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import Footer, Header, Log, Static, TabbedContent, TabPane
    from textual.containers import Vertical
except ImportError as exc:
    raise ImportError(
        "Install TUI extras: pip install 'devsper[tui]'"
    ) from exc


BANNER = """\
  ██████╗ ███████╗██╗   ██╗███████╗██████╗ ███████╗██████╗
  ██╔══██╗██╔════╝██║   ██║██╔════╝██╔══██╗██╔════╝██╔══██╗
  ██║  ██║█████╗  ██║   ██║███████╗██████╔╝█████╗  ██████╔╝
  ██║  ██║██╔══╝  ╚██╗ ██╔╝╚════██║██╔═══╝ ██╔══╝  ██╔══██╗
  ██████╔╝███████╗ ╚████╔╝ ███████║██║     ███████╗██║  ██║
  ╚═════╝ ╚══════╝  ╚═══╝  ╚══════╝╚═╝     ╚══════╝╚═╝  ╚═╝"""


class DevSperApp(App[None]):
    """Main devsper TUI application.

    Connects to a running workflow via its Unix inspect socket
    and renders live graph state, events, and agent output.
    """

    TITLE = "devsper runtime"
    SUB_TITLE = "self-evolving AI workflow engine"

    CSS = """
    Screen {
        background: #0d1117;
    }
    #banner {
        color: #58a6ff;
        padding: 1 2;
        text-style: bold;
    }
    #status-bar {
        color: #8b949e;
        background: #161b22;
        padding: 0 2;
        height: 1;
    }
    #status-bar.running {
        color: #3fb950;
    }
    #event-log {
        border: solid #30363d;
        height: 1fr;
    }
    #agent-log {
        border: solid #30363d;
        height: 1fr;
    }
    TabbedContent {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, extra_args: list[str] | None = None) -> None:
        super().__init__()
        self._extra_args = extra_args or []
        self._socket_path: Path | None = None
        self._run_id: str | None = None

        # Parse --run-id from extra_args if present
        for i, arg in enumerate(self._extra_args):
            if arg == "--run-id" and i + 1 < len(self._extra_args):
                self._run_id = self._extra_args[i + 1]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            Static(BANNER, id="banner"),
            Static(self._status_text(), id="status-bar"),
            TabbedContent(
                TabPane("Events", Log(id="event-log", highlight=True)),
                TabPane("Agent Output", Log(id="agent-log", highlight=True)),
            ),
        )
        yield Footer()

    def on_mount(self) -> None:
        event_log = self.query_one("#event-log", Log)
        event_log.write_line("devsper TUI started.")
        event_log.write_line("")

        if self._run_id:
            event_log.write_line(f"Connecting to run: {self._run_id}")
            self._try_connect_socket()
        else:
            event_log.write_line(
                "No active run. Start one with:\n"
                "  devsper run workflow.devsper\n"
            )
            event_log.write_line(
                "The Rust runtime streams events via --inspect-socket\n"
                "when launched. Pass --run-id <id> to connect."
            )

    def _status_text(self) -> str:
        if self._run_id:
            return f"Run: {self._run_id}"
        return "Status: idle — no active run"

    def _try_connect_socket(self) -> None:
        """Attempt to read from the inspect socket for the given run."""
        if not self._run_id:
            return
        socket_path = Path(f"/tmp/devsper-{self._run_id}.sock")
        if socket_path.exists():
            self.set_interval(0.5, self._poll_socket)
        else:
            log = self.query_one("#event-log", Log)
            log.write_line(
                f"Socket not found: {socket_path}\n"
                "Waiting for workflow to start..."
            )
            # Retry after a delay
            self.set_timer(2.0, self._try_connect_socket)

    async def _poll_socket(self) -> None:
        """Poll the Unix inspect socket for new events (stub)."""
        # Full implementation reads JSON-RPC stream from socket
        # Stub: just show that connection is active
        pass

    def action_refresh(self) -> None:
        log = self.query_one("#event-log", Log)
        log.write_line("Refreshed.")

    def action_quit(self) -> None:
        self.exit()
