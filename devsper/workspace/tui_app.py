"""Textual-based interactive coding interface for devsper.

Claude Code-style layout:
  • Full-screen scrollable conversation log
  • Sticky input bar at the bottom with voice indicator
  • Tool-call events stream in-line as the swarm executes
  • Keyboard shortcuts mirroring common terminal AI tools

Usage (internal — launched by devsper/cli/main.py)::

    from devsper.workspace.tui_app import DevsperApp
    app = DevsperApp(workspace, session)
    app.run()
"""

from __future__ import annotations

import copy
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message as _TMsg
from textual.widgets import Footer, Input, Label, RichLog, Static

if TYPE_CHECKING:
    from devsper.workspace.context import WorkspaceContext
    from devsper.workspace.session import SessionHistory


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
Screen {
    background: #0d0f14;
    layers: base overlay;
}

/* ── Header ─────────────────────────────────────────────────────────── */
#header {
    height: 1;
    background: #1a1d27;
    padding: 0 2;
    border-bottom: tall #2a2d3e;
    layout: horizontal;
}

#header-logo {
    color: #7c6af7;
    text-style: bold;
    width: auto;
}

#header-sep {
    color: #3a3d52;
    width: auto;
    padding: 0 1;
}

#header-project {
    color: #e2e8f0;
    text-style: bold;
    width: auto;
}

#header-branch {
    color: #64748b;
    width: auto;
    padding: 0 1;
}

#header-spacer {
    width: 1fr;
}

#header-model {
    color: #475569;
    width: auto;
    text-align: right;
}

/* ── Conversation log ────────────────────────────────────────────────── */
#conversation {
    height: 1fr;
    background: #0d0f14;
    padding: 1 3;
    scrollbar-color: #2a2d3e #0d0f14;
    scrollbar-size: 1 1;
    border: none;
}

/* ── Status bar (above input) ────────────────────────────────────────── */
#status-bar {
    height: 1;
    background: #111420;
    padding: 0 3;
    border-top: tall #1e2130;
    layout: horizontal;
}

#status-text {
    color: #475569;
    width: 1fr;
    text-style: italic;
}

#status-voice {
    color: #f59e0b;
    width: auto;
    display: none;
}

#status-voice.active {
    display: block;
}

#status-session {
    color: #334155;
    width: auto;
}

/* ── Input row ───────────────────────────────────────────────────────── */
#input-row {
    height: 3;
    background: #111420;
    padding: 0 3;
    layout: horizontal;
    align: left middle;
    border-top: tall #1e2130;
}

#input-prefix {
    color: #7c6af7;
    text-style: bold;
    width: auto;
    padding: 0 1 0 0;
}

#user-input {
    width: 1fr;
    border: none;
    background: transparent;
    color: #e2e8f0;
    padding: 0;
}

#user-input:focus {
    border: none;
    background: transparent;
}

#voice-badge {
    color: #374151;
    width: auto;
    padding: 0 0 0 2;
}
"""


# ---------------------------------------------------------------------------
# Thread → UI messages
# ---------------------------------------------------------------------------

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


class StatusUpdate(_TMsg):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


# ---------------------------------------------------------------------------
# DevsperApp
# ---------------------------------------------------------------------------

class DevsperApp(App):
    """devsper interactive coding interface."""

    CSS = _CSS
    TITLE = "devsper"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+l", "clear_screen", "Clear"),
        Binding("ctrl+e", "edit_in_editor", "Edit in $EDITOR"),
        Binding("f1", "show_help", "Help"),
    ]

    def __init__(
        self,
        workspace: "WorkspaceContext",
        session: "SessionHistory",
        new_session: bool = False,
    ) -> None:
        super().__init__()
        self.workspace = workspace
        self.session = session
        self._new_session = new_session
        self._busy = False
        self._recording = False
        self._voice = None
        self._intelligence = None
        self._last_space_t: float = 0.0
        self._hold_timer = None
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
        p = self.workspace.project_name
        branch = self._git_branch()
        voice_hint = "  ⎵ voice" if (self._voice and self._voice.available) else ""

        yield Horizontal(
            Static("devsper", id="header-logo"),
            Static("›", id="header-sep"),
            Static(p, id="header-project"),
            Static(branch, id="header-branch"),
            Static("", id="header-spacer"),
            Static("claude-sonnet", id="header-model"),
            id="header",
        )
        yield RichLog(id="conversation", wrap=True, markup=True, highlight=True, auto_scroll=True)
        yield Horizontal(
            Label("", id="status-text"),
            Label("🎤 recording…", id="status-voice"),
            Label("", id="status-session"),
            id="status-bar",
        )
        yield Horizontal(
            Static("›", id="input-prefix"),
            Input(placeholder="ask anything…", id="user-input"),
            Static(voice_hint, id="voice-badge"),
            id="input-row",
        )
        yield Footer()

    def on_mount(self) -> None:
        if self._new_session:
            self.session.start_new_session()
        else:
            self.session.load_last_session()

        self._update_status_session()
        self._print_banner()
        self.query_one("#user-input", Input).focus()

        # Pre-compile the Swift binary in the background so it's ready on first
        # Space press — avoids the "starts on release" perception from compile lag.
        if self._voice and self._voice._dictation:
            threading.Thread(
                target=self._voice._dictation.ensure_compiled, daemon=True
            ).start()

    def on_unmount(self) -> None:
        """Kill any in-progress Swift dictation process when app closes."""
        self._kill_voice_proc()

    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        log = self.query_one("#conversation", RichLog)
        try:
            from devsper import __version__
            ver = __version__
        except Exception:
            ver = "?"

        has_md = self.workspace.md_content is not None
        n_facts = self._intelligence.fact_count() if self._intelligence else 0

        # Use Text.assemble to avoid Rich mis-parsing version numbers as markup
        from rich.text import Text
        banner = Text()
        banner.append("devsper", style="bold #7c6af7")
        banner.append(f" v{ver}", style="#94a3b8")
        banner.append("  ·  ", style="#334155")
        banner.append(self.workspace.project_name, style="bold #e2e8f0")
        log.write(banner)

        if has_md:
            log.write("[#22c55e]  ✓ devsper.md loaded[/]")
        else:
            log.write("[#f59e0b]  ⚠ no devsper.md[/]  [#334155]→ /init to generate[/]")

        if n_facts:
            log.write(f"[#334155]  {n_facts} memory facts loaded[/]")

        if self._voice and self._voice.available:
            log.write("[#334155]  🎤 voice ready — press Space at empty prompt[/]")

        log.write("")
        log.write("[#1e2130]" + "─" * 60 + "[/]")
        log.write("")

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    @on(Input.Submitted, "#user-input")
    def handle_submit(self, event: Input.Submitted) -> None:
        if self._recording:
            # Enter while holding: stop recording, submit whatever was transcribed
            self._stop_recording()
            return
        text = event.value.strip()
        event.input.clear()
        if not text:
            return
        if self._busy:
            self._log("[#f59e0b]Still working — please wait.[/]")
            return
        if text.startswith("/"):
            self._handle_slash(text)
        else:
            self._run_turn(text)

    @on(Input.Changed, "#user-input")
    def handle_input_changed(self, event: Input.Changed) -> None:
        # Space on empty input → push-to-talk
        if event.value != " " or self._busy:
            return
        if not self._voice or not self._voice.available:
            return
        event.input.clear()
        if not self._recording:
            # Initial press — start recording and begin hold-detection timer
            self._last_space_t = time.monotonic()
            self._start_voice()
        else:
            # Key-repeat while holding — keep alive
            self._last_space_t = time.monotonic()

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    def _start_voice(self) -> None:
        self._recording = True
        self._set_voice_active(True)
        self._set_status("recording… release Space to finish")
        # Timer polls every 120 ms; if no Space key-repeat for 280 ms → released
        self._hold_timer = self.set_interval(0.12, self._check_space_released)

        def _record():
            try:
                text = self._voice._record(tui_mode=True)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).debug("voice error: %s", exc)
                text = ""
            self.post_message(VoiceResult(text))

        threading.Thread(target=_record, daemon=True).start()

    def _check_space_released(self) -> None:
        """Timer callback — fires every 120 ms while recording."""
        if not self._recording:
            self._cancel_hold_timer()
            return
        if time.monotonic() - self._last_space_t > 0.28:
            # Space was released → stop the dictation process
            self._cancel_hold_timer()
            self._stop_recording()

    def _stop_recording(self) -> None:
        """Send SIGTERM to Swift — it will flush its final transcript to stdout."""
        self._cancel_hold_timer()
        self._kill_voice_proc()

    def _cancel_hold_timer(self) -> None:
        if self._hold_timer is not None:
            try:
                self._hold_timer.stop()
            except Exception:
                pass
            self._hold_timer = None

    def _kill_voice_proc(self) -> None:
        """Terminate the Swift dictation subprocess."""
        try:
            if self._voice and self._voice._dictation:
                proc = self._voice._dictation._current_proc
                if proc and proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=2)
        except Exception:
            pass

    def on_voice_result(self, msg: VoiceResult) -> None:
        self._recording = False
        self._cancel_hold_timer()
        self._set_voice_active(False)
        self._set_status("")
        inp = self.query_one("#user-input", Input)
        if msg.text:
            # Put transcript in input field — user can edit before submitting
            inp.value = msg.text
            inp.cursor_position = len(msg.text)
        else:
            self._log("[#64748b]  Nothing heard.[/]")
        inp.disabled = False
        inp.focus()

    def _set_voice_active(self, active: bool) -> None:
        badge = self.query_one("#status-voice")
        if active:
            badge.add_class("active")
        else:
            badge.remove_class("active")

    # ------------------------------------------------------------------
    # Turn execution
    # ------------------------------------------------------------------

    def _run_turn(self, user_text: str) -> None:
        log = self.query_one("#conversation", RichLog)
        log.write("")
        log.write(f"[bold #93c5fd]  you[/]")
        log.write(f"[#cbd5e1]  {user_text}[/]")
        log.write("")
        self.session.save_turn("user", user_text)
        self._set_busy(True)
        self._set_status("thinking…")
        self._execute_turn(user_text)

    @work(thread=True)
    def _execute_turn(self, user_text: str) -> None:
        from devsper.workspace.display import CallbackEventLog, format_event_line

        def _on_event(evt: dict) -> None:
            line = format_event_line(evt)
            if line:
                self.post_message(AppendLine(f"[#475569]  {line}[/]"))

        event_log = CallbackEventLog(callback=_on_event)
        swarm = self._make_swarm(event_log)
        task = self._build_task(user_text)

        try:
            result = swarm.run(task)
            answer = self._extract_answer(result)
        except Exception as exc:
            answer = f"[#ef4444]Error: {exc}[/]"

        self.post_message(TurnDone(answer or ""))

    def on_turn_done(self, msg: TurnDone) -> None:
        log = self.query_one("#conversation", RichLog)
        if msg.answer:
            log.write(f"[bold #a78bfa]  devsper[/]")
            log.write(f"[#e2e8f0]{self._indent(msg.answer)}[/]")
            log.write("")
            log.write("[#1e2130]" + "─" * 60 + "[/]")
            log.write("")
        self.session.save_turn("assistant", msg.answer)
        self._set_busy(False)
        self._set_status("")

        if self._intelligence and msg.answer:
            def _extract():
                try:
                    self._intelligence.extract_and_store("", msg.answer)
                except Exception:
                    pass
            threading.Thread(target=_extract, daemon=True).start()

    def on_append_line(self, msg: AppendLine) -> None:
        self.query_one("#conversation", RichLog).write(msg.text, markup=msg.markup)

    def on_status_update(self, msg: StatusUpdate) -> None:
        self._set_status(msg.text)

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    def _handle_slash(self, text: str) -> None:
        parts = text.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        dispatch = {
            "/exit": lambda: self.action_quit(),
            "/quit": lambda: self.action_quit(),
            "/new": lambda: self._cmd_new(),
            "/sessions": lambda: self._show_sessions(),
            "/memory": lambda: self._query_memory(arg.strip()),
            "/init": lambda: self._run_init(force=arg.strip() == "--force"),
            "/mission": lambda: self._run_mission(arg.strip()),
            "/council": lambda: self._run_council(arg.strip()),
            "/help": lambda: self._show_help(),
            "/clear": lambda: self.action_clear_screen(),
        }
        fn = dispatch.get(cmd)
        if fn:
            fn()
        else:
            self._log(f"[#64748b]Unknown: {cmd}  —  /help for commands[/]")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_quit(self) -> None:
        self._kill_voice_proc()
        self.session.close()
        self.exit()

    def action_new_session(self) -> None:
        self._cmd_new()

    def action_clear_screen(self) -> None:
        self.query_one("#conversation", RichLog).clear()
        self._print_banner()

    def action_show_help(self) -> None:
        self._show_help()

    def action_edit_in_editor(self) -> None:
        """Open current input content in $EDITOR; paste result back on save."""
        inp = self.query_one("#user-input", Input)
        current = inp.value

        editor = (
            os.environ.get("EDITOR")
            or os.environ.get("VISUAL")
            or "nvim"
        )

        with tempfile.NamedTemporaryFile(
            suffix=".md", mode="w", delete=False, prefix="devsper_prompt_"
        ) as f:
            f.write(current)
            tmpfile = f.name

        try:
            with self.suspend():
                import subprocess
                subprocess.run([editor, tmpfile], check=False)
            with open(tmpfile) as f:
                new_text = f.read().rstrip("\n")
            inp.value = new_text
            inp.cursor_position = len(new_text)
        except Exception as exc:
            self._log(f"[#ef4444]  editor error: {exc}[/]")
        finally:
            Path(tmpfile).unlink(missing_ok=True)
        inp.focus()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log(self, text: str) -> None:
        self.query_one("#conversation", RichLog).write(text)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        inp = self.query_one("#user-input", Input)
        inp.disabled = busy  # voice recording manages its own disabled state

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#status-text", Label).update(f"  {text}" if text else "")
        except Exception:
            pass

    def _update_status_session(self) -> None:
        try:
            sid = getattr(self.session, "_session_id", "")
            label = f"{sid[:8]}  " if sid else ""
            self.query_one("#status-session", Label).update(label)
        except Exception:
            pass

    def _indent(self, text: str, spaces: int = 2) -> str:
        pad = " " * spaces
        return "\n".join(pad + line for line in text.splitlines())

    def _git_branch(self) -> str:
        try:
            import subprocess
            r = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace.project_root,
                capture_output=True, text=True, timeout=2,
            )
            b = r.stdout.strip()
            return f"git:{b}" if b and b != "HEAD" else ""
        except Exception:
            return ""

    def _build_task(self, user_message: str) -> str:
        parts: list[str] = []
        if self.workspace.md_content:
            parts.append(f"<project_instructions>\n{self.workspace.md_content}\n</project_instructions>")
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

    def _extract_answer(self, result) -> str:
        if not isinstance(result, dict):
            return str(result)
        for key in ("answer", "result", "output", "summary", "response"):
            val = result.get(key)
            if val and isinstance(val, str):
                return val
        parts = [v.strip() for v in result.values() if isinstance(v, str) and v.strip()]
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Slash helpers
    # ------------------------------------------------------------------

    def _cmd_new(self) -> None:
        sid = self.session.start_new_session()
        self._update_status_session()
        self._log(f"[#22c55e]  ✓ new session {sid[:8]}[/]")

    def _show_sessions(self) -> None:
        sessions = self.session.list_sessions()
        if not sessions:
            self._log("[#64748b]  no sessions[/]")
            return
        active = self.session._session_id
        self._log("[bold #7c6af7]  sessions[/]")
        for s in sessions:
            mark = "  [#22c55e]← active[/]" if s["session_id"] == active else ""
            self._log(
                f"  [#475569]{s['session_id'][:8]}[/]"
                f"  [#334155]{s['turn_count']} turns[/]{mark}"
            )

    def _query_memory(self, query: str) -> None:
        try:
            from devsper.memory.memory_store import get_default_store
            store = get_default_store()
            ns = f"project:{self.workspace.project_id}"
            results = (
                store.search(query, namespace=ns, top_k=5)
                if query
                else store.list(namespace=ns, limit=10)
            )
            if not results:
                self._log("[#64748b]  no memories found[/]")
            else:
                self._log("[bold #7c6af7]  memory[/]")
                for i, item in enumerate(results, 1):
                    text = getattr(item, "text", None) or str(item)
                    self._log(f"  [#475569]{i}.[/] {text[:120]}")
        except Exception as exc:
            self._log(f"[#ef4444]  memory unavailable: {exc}[/]")

    def _run_init(self, force: bool = False) -> None:
        md_path = self.workspace.project_root / "devsper.md"
        if md_path.exists() and not force:
            self._log(
                "[#f59e0b]  devsper.md already exists[/]"
                "  [#334155]→ /init --force to regenerate[/]"
            )
            return
        self._log("[#475569]  generating devsper.md…[/]")
        self._set_busy(True)

        def _do():
            try:
                from devsper.cli.init import run_init_md
                rc = run_init_md(self.workspace.project_root, overwrite=force)
                self.post_message(
                    AppendLine("[#22c55e]  ✓ devsper.md ready[/]" if rc == 0 else "[#ef4444]  init failed[/]")
                )
            except Exception as exc:
                self.post_message(AppendLine(f"[#ef4444]  init error: {exc}[/]"))
            finally:
                self.post_message(TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    def _run_mission(self, arg: str) -> None:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            self._log("[#64748b]  usage: /mission r2c <goal>[/]")
            return
        mission_type, goal = parts[0].lower(), parts[1]
        if mission_type not in ("r2c", "research-code", "research_to_code"):
            self._log(f"[#64748b]  unknown mission: {mission_type}[/]")
            return
        self._log(f"[#475569]  research → code: {goal[:70]}…[/]")
        self._set_busy(True)

        def _do():
            try:
                from devsper.council.research_to_code import ResearchToCodeMission
                result = ResearchToCodeMission().run(goal)
                self.post_message(AppendLine(f"[#7c6af7]  summary:[/] {result.handoff.summary}"))
                self.post_message(TurnDone(result.final_code))
            except Exception as exc:
                self.post_message(AppendLine(f"[#ef4444]  mission failed: {exc}[/]"))
                self.post_message(TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    def _run_council(self, task: str) -> None:
        if not task:
            self._log("[#64748b]  usage: /council <task>[/]")
            return
        self._log("[#475569]  council: draft → critique → synthesize…[/]")
        self._set_busy(True)

        def _do():
            try:
                from devsper.council import Council, CouncilConfig
                result = Council(CouncilConfig()).run(task)
                self.post_message(TurnDone(result.final))
            except Exception as exc:
                self.post_message(AppendLine(f"[#ef4444]  council failed: {exc}[/]"))
                self.post_message(TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    def _show_help(self) -> None:
        self._log("""
[bold #7c6af7]  commands[/]
  [#93c5fd]/init[/] [#475569][--force][/]    generate devsper.md
  [#93c5fd]/new[/]              new session
  [#93c5fd]/sessions[/]         list sessions
  [#93c5fd]/memory[/] [#475569][query][/]    search project memory
  [#93c5fd]/mission r2c[/]      research → code pipeline
  [#93c5fd]/council[/] [#475569]<task>[/]   draft → critique → synthesize
  [#93c5fd]/clear[/]            clear screen
  [#93c5fd]/help[/]             this message
  [#93c5fd]/exit[/]             quit

[bold #7c6af7]  voice[/]
  hold [#f59e0b]Space[/]   [#475569]→ speak while held, release to finish[/]
  [#f59e0b]Enter[/]        [#475569]→ stop early, transcript lands in input[/]
  transcript appears in input — edit then [#f59e0b]Enter[/] to submit

[bold #7c6af7]  keys[/]
  [#f59e0b]Ctrl+E[/]  open in $EDITOR
  [#f59e0b]Ctrl+N[/]  new session  [#475569]·[/]  [#f59e0b]Ctrl+L[/]  clear  [#475569]·[/]  [#f59e0b]Ctrl+C[/]  quit
""")
