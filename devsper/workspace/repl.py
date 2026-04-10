"""CodeREPL — interactive swarm-backed coding agent loop."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from devsper.workspace.context import WorkspaceContext
from devsper.workspace.session import SessionHistory
from devsper.workspace.display import CallbackEventLog, ToolCallDisplay


_HELP_TEXT = """\
Slash-commands:
  /new          Start a fresh session (keeps semantic memory)
  /sessions     List past sessions for this project
  /memory       Query project semantic memory
  /help         Show this help
  /exit /quit   Exit
"""


class CodeREPL:
    """Interactive REPL backed by the devsper Swarm engine.

    Usage::

        workspace = WorkspaceContext.discover(Path.cwd())
        session = SessionHistory(workspace.storage_dir)
        repl = CodeREPL(workspace, session)
        repl.start()
    """

    def __init__(
        self,
        workspace: WorkspaceContext,
        session: SessionHistory,
        new_session: bool = False,
    ) -> None:
        self.workspace = workspace
        self.session = session
        self._new_session = new_session
        self._display = ToolCallDisplay()
        self._console = self._display._console

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Run the REPL until the user exits."""
        if self._new_session:
            self.session.start_new_session()
        else:
            self.session.load_last_session()

        self._print_banner()

        while True:
            try:
                user_input = self._prompt()
            except (EOFError, KeyboardInterrupt):
                self._print("\nBye.")
                break

            text = user_input.strip()
            if not text:
                continue

            if text.startswith("/"):
                should_exit = self._handle_slash(text)
                if should_exit:
                    break
            else:
                try:
                    self._run_turn(text)
                except KeyboardInterrupt:
                    self._print("\n[dim]Interrupted.[/]", markup=True)

        self.session.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prompt(self) -> str:
        project = self.workspace.project_name
        try:
            if self._console:
                return self._console.input(f"[bold cyan]{project}[/] [dim]>[/] ")
            else:
                return input(f"{project} > ")
        except Exception:
            return input(f"{project} > ")

    def _handle_slash(self, text: str) -> bool:
        """Handle slash commands. Returns True if the REPL should exit."""
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit"):
            self._print("Bye.")
            return True

        if cmd == "/new":
            sid = self.session.start_new_session()
            self._print(f"Started new session {sid[:8]}.")
            return False

        if cmd == "/sessions":
            sessions = self.session.list_sessions()
            if not sessions:
                self._print("No sessions found.")
            else:
                active = self.session._session_id
                for s in sessions:
                    marker = " (active)" if s["session_id"] == active else ""
                    self._print(
                        f"  {s['session_id'][:8]}  {s['turn_count']} turns{marker}"
                    )
            return False

        if cmd == "/memory":
            self._query_memory(arg.strip())
            return False

        if cmd == "/help":
            self._print(_HELP_TEXT)
            return False

        self._print(f"Unknown command: {cmd}. Type /help for commands.")
        return False

    def _run_turn(self, user_message: str) -> None:
        """Save user turn, run swarm, print result, save assistant turn."""
        self.session.save_turn("user", user_message)

        task = self._build_task(user_message)

        # Build event log with display callback
        event_log = CallbackEventLog(callback=self._display.on_event)

        from devsper.swarm.swarm import Swarm

        swarm = self._make_swarm(event_log)

        result = swarm.run(task)

        # Extract answer text
        answer = self._extract_answer(result)
        if answer:
            self._print("")
            self._print(answer)

        self.session.save_turn("assistant", answer or str(result))

    def _build_task(self, user_message: str) -> str:
        """Build the full task string injecting project context and history."""
        parts: list[str] = []

        if self.workspace.md_content:
            parts.append(
                f"<project_instructions>\n{self.workspace.md_content}\n</project_instructions>"
            )

        history = self.session.format_history_for_context(max_turns=10)
        if history:
            parts.append(f"<conversation_history>\n{history}\n</conversation_history>")

        parts.append(user_message)
        return "\n\n".join(parts)

    def _make_swarm(self, event_log: CallbackEventLog):
        """Create a Swarm instance with project-scoped memory namespace."""
        from devsper.config import get_config
        from devsper.swarm.swarm import Swarm

        try:
            cfg = get_config()
            # Deep copy so we don't mutate the global config
            cfg = copy.deepcopy(cfg)
            # Scope memory to this project via agent identity namespace
            if hasattr(cfg, "agents") and hasattr(cfg.agents, "identity"):
                cfg.agents.identity.memory_namespace = f"project:{self.workspace.project_id}"
        except Exception:
            cfg = None

        return Swarm(event_log=event_log, config=cfg)

    def _extract_answer(self, result: dict) -> str:
        """Pull a readable answer string from Swarm result dict."""
        if not isinstance(result, dict):
            return str(result)
        # Try common result keys in priority order
        for key in ("answer", "result", "output", "summary", "response"):
            val = result.get(key)
            if val and isinstance(val, str):
                return val
        # Concatenate all string values from tasks
        parts = []
        for val in result.values():
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
        return "\n\n".join(parts) if parts else ""

    def _query_memory(self, query: str) -> None:
        """Search project semantic memory."""
        try:
            from devsper.memory.memory_store import get_default_store

            store = get_default_store()
            ns = f"project:{self.workspace.project_id}"
            if query:
                results = store.search(query, namespace=ns, top_k=5)
            else:
                results = store.list(namespace=ns, limit=10)
            if not results:
                self._print("No memories found.")
            else:
                for i, item in enumerate(results, 1):
                    text = getattr(item, "text", None) or str(item)
                    self._print(f"  {i}. {text[:120]}")
        except Exception as exc:
            self._print(f"Memory unavailable: {exc}")

    def _print_banner(self) -> None:
        """Print the startup banner."""
        try:
            from devsper import __version__
        except Exception:
            __version__ = "?"

        project = self.workspace.project_name
        has_md = self.workspace.md_content is not None
        md_status = "devsper.md loaded" if has_md else "no devsper.md"
        hint = "" if has_md else "\n  → Run [cyan]devsper init --md[/] to generate project instructions."

        banner = (
            f"\n[bold]devsper v{__version__}[/] · [cyan]{project}[/]  [dim]{md_status}[/]"
            + hint
            + "\n"
        )
        self._print(banner, markup=True)

    def _print(self, text: str, *, markup: bool = False) -> None:
        if self._console:
            self._console.print(text, markup=markup)
        else:
            import re
            print(re.sub(r"\[/?[^\]]*\]", "", text))
