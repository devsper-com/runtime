"""Textual-based interactive coding interface for devsper.

Layout mirrors Claude Code: scrollable conversation log fills the screen,
a single-line input bar docks at the bottom, tool-call events stream in
inline as the swarm works.

Usage (internal — launched by devsper/cli/main.py)::

    from devsper.workspace.tui_app import DevsperApp
    app = DevsperApp(workspace, session)
    app.run()
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Input, RichLog, Static

if TYPE_CHECKING:
    from devsper.workspace.context import WorkspaceContext
    from devsper.workspace.session import SessionHistory


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
Screen {
    background: $background;
}

#header-bar {
    height: 1;
    background: $primary-darken-3;
    padding: 0 2;
    color: $text;
}

#project-name {
    color: $accent;
    text-style: bold;
}

#header-meta {
    color: $text-muted;
    text-align: right;
    width: 1fr;
}

#conversation {
    height: 1fr;
    padding: 1 2;
    scrollbar-gutter: stable;
}

#input-container {
    height: 3;
    border-top: tall $primary-darken-2;
    padding: 0 2;
    background: $surface;
    align: left middle;
}

#prompt-prefix {
    width: auto;
    color: $accent;
    text-style: bold;
    padding: 0 1 0 0;
}

#user-input {
    width: 1fr;
    border: none;
    background: transparent;
    padding: 0;
}

#voice-hint {
    width: auto;
    color: $text-muted;
    padding: 0 0 0 1;
    display: none;
}

#voice-hint.visible {
    display: block;
}

.user-msg {
    color: $accent;
    text-style: bold;
    margin-top: 1;
}

.user-text {
    padding: 0 0 0 2;
    margin-bottom: 1;
}

.tool-line {
    color: $text-muted;
    padding: 0 0 0 2;
}

.answer-text {
    padding: 0 0 0 2;
    margin-bottom: 1;
}

.separator {
    height: 1;
    color: $primary-darken-2;
}

.status-thinking {
    color: $warning;
    padding: 0 0 0 2;
}
"""


# ---------------------------------------------------------------------------
# Custom messages for thread → UI communication
# ---------------------------------------------------------------------------

from textual.message import Message as _TMsg


class AppendLine(_TMsg):
    def __init__(self, text: str, markup: bool = True) -> None:
        super().__init__()
        self.text = text
        self.markup = markup


class TurnDone(_TMsg):
    def __init__(self, answer: str) -> None:
        super().__init__()
        self.answer = answer


class VoiceResult(_TMsg):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


# ---------------------------------------------------------------------------
# DevsperApp
# ---------------------------------------------------------------------------

class DevsperApp(App):
    """Claude Code-style Textual interface for devsper."""

    CSS = _CSS

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("ctrl+h", "show_help", "Help"),
    ]

    def __init__(
        self,
        workspace: WorkspaceContext,
        session: SessionHistory,
        new_session: bool = False,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.session = session
        self._new_session = new_session
        self._busy = False
        self._voice = None
        self._intelligence = None
        self._init_subsystems()

    def _init_subsystems(self) -> None:
        try:
            from devsper.workspace.living import WorkspaceIntelligence
            self._intelligence = WorkspaceIntelligence(self.workspace)
        except Exception:
            pass
        try:
            from devsper.workspace.voice import VoiceInput
            self._voice = VoiceInput(console=None)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        project = self.workspace.project_name
        voice_str = "  🎤" if (self._voice and self._voice.available) else ""

        yield Horizontal(
            Static(f"[bold]{project}[/]", id="project-name"),
            Static(f"devsper  {voice_str}", id="header-meta"),
            id="header-bar",
        )
        yield RichLog(id="conversation", wrap=True, markup=True, highlight=False)
        yield Horizontal(
            Static(f"{project} ›", id="prompt-prefix"),
            Input(placeholder="message… (Space for voice)", id="user-input"),
            Static("🎤 space", id="voice-hint"),
            id="input-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        if self._new_session:
            self.session.start_new_session()
        else:
            self.session.load_last_session()

        self._print_banner()
        self.query_one("#user-input", Input).focus()

        # Show voice hint if available
        if self._voice and self._voice.available:
            self.query_one("#voice-hint").add_class("visible")

    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        log = self.query_one("#conversation", RichLog)
        try:
            from devsper import __version__
        except Exception:
            __version__ = "?"

        has_md = self.workspace.md_content is not None
        n_facts = self._intelligence.fact_count() if self._intelligence else 0

        md_note = "[green]devsper.md loaded[/]" if has_md else "[yellow]no devsper.md[/]"
        facts_note = f"  ·  {n_facts} facts" if n_facts else ""
        log.write(f"[bold]devsper v{__version__}[/]  ·  {md_note}{facts_note}\n")

        if not has_md:
            log.write("[dim]  → /init to generate project instructions[/]\n")
        log.write("")

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    @on(Input.Submitted, "#user-input")
    def handle_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        if self._busy:
            self._log("[dim]Still working — please wait.[/]")
            return
        if text.startswith("/"):
            self._handle_slash(text)
        else:
            self._run_turn(text)

    @on(Input.Changed, "#user-input")
    def handle_input_changed(self, event: Input.Changed) -> None:
        # Intercept Space at empty input → voice
        if (
            event.value == " "
            and self._voice
            and self._voice.available
            and not self._busy
        ):
            event.input.clear()
            self._start_voice()

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    def _start_voice(self) -> None:
        self._log("  [bold yellow]🎤[/] [dim]Recording — speak, then pause…[/]")
        self._set_busy(True)

        def _record():
            try:
                text = self._voice.record()
            except Exception:
                text = ""
            self.post_message(VoiceResult(text))

        threading.Thread(target=_record, daemon=True).start()

    def on_voice_result(self, msg: VoiceResult) -> None:
        self._set_busy(False)
        if msg.text:
            self._run_turn(msg.text)
        else:
            self._log("  [dim]Nothing heard — try again.[/]")

    # ------------------------------------------------------------------
    # Turn execution
    # ------------------------------------------------------------------

    def _run_turn(self, user_text: str) -> None:
        log = self.query_one("#conversation", RichLog)
        log.write(f"\n[bold cyan]You[/]")
        log.write(f"  {user_text}\n")
        self.session.save_turn("user", user_text)
        self._set_busy(True)
        self._execute_turn(user_text)

    @work(thread=True)
    def _execute_turn(self, user_text: str) -> None:
        """Run the swarm in a worker thread; post events back to UI."""
        from devsper.workspace.display import CallbackEventLog, format_event_line

        def _on_event(event_dict: dict) -> None:
            line = format_event_line(event_dict)
            if line:
                self.post_message(AppendLine(f"[dim]{line}[/]"))

        event_log = CallbackEventLog(callback=_on_event)
        swarm = self._make_swarm(event_log)

        task = self._build_task(user_text)
        self.post_message(AppendLine("  [dim]● Thinking…[/]"))

        try:
            result = swarm.run(task)
            answer = self._extract_answer(result)
        except Exception as exc:
            answer = f"[red]Error: {exc}[/]"

        self.post_message(TurnDone(answer or ""))

    def on_turn_done(self, msg: TurnDone) -> None:
        log = self.query_one("#conversation", RichLog)
        if msg.answer:
            log.write(f"\n[bold green]devsper[/]")
            log.write(f"  {msg.answer}\n")
        self.session.save_turn("assistant", msg.answer)
        self._set_busy(False)

        # Non-blocking fact extraction
        if self._intelligence and msg.answer:
            def _extract():
                try:
                    self._intelligence.extract_and_store("", msg.answer)
                except Exception:
                    pass
            threading.Thread(target=_extract, daemon=True).start()

    def on_append_line(self, msg: AppendLine) -> None:
        log = self.query_one("#conversation", RichLog)
        log.write(msg.text, markup=msg.markup)

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    def _handle_slash(self, text: str) -> None:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit"):
            self.exit()
        elif cmd == "/new":
            sid = self.session.start_new_session()
            self._log(f"New session [cyan]{sid[:8]}[/]")
        elif cmd == "/sessions":
            self._show_sessions()
        elif cmd == "/memory":
            self._query_memory(arg.strip())
        elif cmd == "/init":
            self._run_init(force=arg.strip() == "--force")
        elif cmd == "/mission":
            self._run_mission(arg.strip())
        elif cmd == "/council":
            self._run_council(arg.strip())
        elif cmd == "/help":
            self._show_help()
        elif cmd == "/clear":
            self.action_clear()
        else:
            self._log(f"[dim]Unknown: {cmd}. /help for commands.[/]")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_quit(self) -> None:
        self.session.close()
        self.exit()

    def action_new_session(self) -> None:
        sid = self.session.start_new_session()
        self._log(f"New session [cyan]{sid[:8]}[/]")

    def action_clear(self) -> None:
        self.query_one("#conversation", RichLog).clear()
        self._print_banner()

    def action_show_help(self) -> None:
        self._show_help()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, text: str) -> None:
        self.query_one("#conversation", RichLog).write(text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        inp = self.query_one("#user-input", Input)
        inp.disabled = busy

    def _build_task(self, user_message: str) -> str:
        parts: list[str] = []
        if self.workspace.md_content:
            parts.append(
                f"<project_instructions>\n{self.workspace.md_content}\n</project_instructions>"
            )
        history = self.session.format_history_for_context(max_turns=10)
        if history:
            parts.append(f"<conversation_history>\n{history}\n</conversation_history>")
        if self._intelligence:
            intel = self._intelligence.load_context()
            if intel:
                parts.append(f"<project_knowledge>\n{intel}\n</project_knowledge>")
        parts.append(user_message)
        return "\n\n".join(parts)

    def _make_swarm(self, event_log):
        from devsper.config import get_config
        from devsper.swarm.swarm import Swarm

        cfg = None
        try:
            cfg = get_config()
            cfg = copy.deepcopy(cfg)
            if hasattr(cfg, "agents") and hasattr(cfg.agents, "identity"):
                cfg.agents.identity.memory_namespace = f"project:{self.workspace.project_id}"
        except Exception:
            cfg = None

        if cfg is not None:
            return Swarm(event_log=event_log, config=cfg)
        return Swarm(
            event_log=event_log,
            worker_model="auto",
            planner_model="auto",
            use_tools=True,
            adaptive=True,
        )

    def _extract_answer(self, result: dict) -> str:
        if not isinstance(result, dict):
            return str(result)
        for key in ("answer", "result", "output", "summary", "response"):
            val = result.get(key)
            if val and isinstance(val, str):
                return val
        parts = [v.strip() for v in result.values() if isinstance(v, str) and v.strip()]
        return "\n\n".join(parts)

    def _show_sessions(self) -> None:
        sessions = self.session.list_sessions()
        if not sessions:
            self._log("[dim]No sessions.[/]")
            return
        active = self.session._session_id
        for s in sessions:
            mark = " [green](active)[/]" if s["session_id"] == active else ""
            self._log(f"  [cyan]{s['session_id'][:8]}[/]  {s['turn_count']} turns{mark}")

    def _query_memory(self, query: str) -> None:
        try:
            from devsper.memory.memory_store import get_default_store
            store = get_default_store()
            ns = f"project:{self.workspace.project_id}"
            results = store.search(query, namespace=ns, top_k=5) if query else store.list(namespace=ns, limit=10)
            if not results:
                self._log("[dim]No memories found.[/]")
            else:
                for i, item in enumerate(results, 1):
                    text = getattr(item, "text", None) or str(item)
                    self._log(f"  {i}. {text[:120]}")
        except Exception as exc:
            self._log(f"[red]Memory unavailable: {exc}[/]")

    def _run_init(self, force: bool = False) -> None:
        md_path = self.workspace.project_root / "devsper.md"
        if md_path.exists() and not force:
            self._log("[yellow]devsper.md exists.[/] Use [cyan]/init --force[/] to regenerate.")
            return
        self._log("[dim]Generating devsper.md…[/]")

        def _do():
            try:
                from devsper.cli.init import run_init_md
                rc = run_init_md(self.workspace.project_root, overwrite=force)
                if rc == 0:
                    self.post_message(AppendLine("[green]devsper.md ready.[/]"))
                else:
                    self.post_message(AppendLine("[red]init failed.[/]"))
            except Exception as exc:
                self.post_message(AppendLine(f"[red]init error: {exc}[/]"))

        threading.Thread(target=_do, daemon=True).start()

    def _run_mission(self, arg: str) -> None:
        parts = arg.split(None, 1)
        if not parts or len(parts) < 2:
            self._log("Usage: /mission r2c <goal>")
            return
        mission_type, goal = parts[0].lower(), parts[1]
        if mission_type not in ("r2c", "research-code", "research_to_code"):
            self._log(f"[dim]Unknown mission: {mission_type}. Available: r2c[/]")
            return
        self._log(f"[dim]Research→Code: {goal[:60]}…[/]")
        self._set_busy(True)

        def _do():
            try:
                from devsper.council.research_to_code import ResearchToCodeMission
                result = ResearchToCodeMission().run(goal)
                self.post_message(AppendLine(f"[bold]Summary:[/] {result.handoff.summary}"))
                self.post_message(TurnDone(result.final_code))
            except Exception as exc:
                self.post_message(AppendLine(f"[red]Mission failed: {exc}[/]"))
                self.post_message(TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    def _run_council(self, task: str) -> None:
        if not task:
            self._log("Usage: /council <task>")
            return
        self._log("[dim]Council: drafting → critiquing → synthesizing…[/]")
        self._set_busy(True)

        def _do():
            try:
                from devsper.council import Council, CouncilConfig
                result = Council(CouncilConfig()).run(task)
                self.post_message(TurnDone(result.final))
            except Exception as exc:
                self.post_message(AppendLine(f"[red]Council failed: {exc}[/]"))
                self.post_message(TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    def _show_help(self) -> None:
        self._log("""
[bold]Slash commands[/]
  /init [--force]   Generate devsper.md
  /new              New session
  /sessions         List sessions
  /memory [query]   Search project memory
  /mission r2c      Research→Code pipeline
  /council <task>   Draft→Critique→Synthesize
  /clear            Clear screen
  /help             This message
  /exit             Quit

[bold]Voice[/]  Press [cyan]Space[/] at empty prompt to record
""")
