"""Textual coding interface for devsper.

Layout:
  • Full-screen scrollable message list (VerticalScroll + per-message widgets)
  • Markdown rendering for assistant responses, Panels for user bubbles
  • Sticky input bar, status bar, key hints in footer
  • Ctrl+Space → voice (Swift / Whisper); Escape → cancel; Ctrl+E → $EDITOR

Usage::
    from devsper.workspace.tui_app import DevsperApp
    DevsperApp(workspace, session).run()
"""

from __future__ import annotations

import copy
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel as RichPanel
from rich.text import Text as RichText
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message as _TMsg
from textual.widgets import Footer, Input, Label, Static

if TYPE_CHECKING:
    from devsper.workspace.context import WorkspaceContext
    from devsper.workspace.session import SessionHistory


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
Screen { background: #0d0f14; }

/* ── Header ── */
#header {
    height: 1;
    background: #0d0f14;
    border-bottom: tall #1a1d2e;
    padding: 0 2;
    layout: horizontal;
    align: left middle;
}
#hd-logo   { color: #7c6af7; text-style: bold; width: auto; }
#hd-sep    { color: #2a2d3e; width: auto; padding: 0 1; }
#hd-proj   { color: #e2e8f0; text-style: bold; width: auto; }
#hd-branch { color: #475569; width: auto; padding: 0 1; }
#hd-fill   { width: 1fr; }
#hd-model  { color: #334155; width: auto; }

/* ── Conversation ── */
#conversation {
    height: 1fr;
    padding: 0 2;
    background: #0d0f14;
}

/* ── Message widgets ── */
.msg-wrap {
    padding: 1 1 0 1;
    width: 100%;
}
.msg-user {
    padding: 1 1 0 1;
    width: 100%;
    align: right middle;
}
.thinking-wrap {
    padding: 0 2;
    color: #475569;
}

/* ── Status + input ── */
#status-bar {
    height: 1;
    background: #0a0c12;
    border-top: tall #1a1d2e;
    padding: 0 3;
    layout: horizontal;
    align: left middle;
}
#status-left  { color: #475569; width: 1fr; text-style: italic; }
#status-voice { color: #f59e0b; text-style: bold; width: auto; display: none; }
#status-voice.active { display: block; }

#input-row {
    height: 3;
    background: #0a0c12;
    padding: 0 2;
    layout: horizontal;
    align: left middle;
    border-top: tall #1a1d2e;
}
#inp-prefix {
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
#user-input:focus { border: none; background: transparent; }
#inp-hint { color: #1e293b; width: auto; padding: 0 0 0 2; }
"""


# ---------------------------------------------------------------------------
# Thread → UI messages
# ---------------------------------------------------------------------------

class _AppendWidget(_TMsg):
    def __init__(self, widget: Static) -> None:
        super().__init__()
        self.widget = widget


class _AppendLine(_TMsg):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class _TurnDone(_TMsg):
    def __init__(self, answer: str) -> None:
        super().__init__()
        self.answer = answer


class _VoiceResult(_TMsg):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class _SetStatus(_TMsg):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


# ---------------------------------------------------------------------------
# Message widgets
# ---------------------------------------------------------------------------

def _user_widget(text: str) -> Static:
    panel = RichPanel(
        f"[#cbd5e1]{text}[/]",
        border_style="#1e3a5f",
        padding=(0, 1),
        title="[bold #60a5fa]you[/]",
        title_align="left",
    )
    return Static(panel, classes="msg-wrap")


def _tool_widget(text: str) -> Static:
    return Static(f"  [#334155]{text}[/]", classes="thinking-wrap")


def _thinking_widget() -> Static:
    return Static("  [#334155 italic]thinking…[/]", classes="thinking-wrap", id="thinking-indicator")


# ---------------------------------------------------------------------------
# DevsperApp
# ---------------------------------------------------------------------------

class DevsperApp(App):
    CSS = _CSS
    TITLE = "devsper"

    BINDINGS = [
        Binding("ctrl+c",     "quit",             "Quit",         priority=True),
        Binding("ctrl+space", "toggle_voice",      "Voice",        show=False),
        Binding("escape",     "cancel_voice",      "Cancel voice", show=False),
        Binding("ctrl+e",     "edit_in_editor",    "Edit in $EDITOR"),
        Binding("ctrl+n",     "new_session",       "New session"),
        Binding("ctrl+l",     "clear_screen",      "Clear"),
        Binding("f1",         "show_help",         "Help"),
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
        branch = self._git_branch()
        has_voice = bool(self._voice and self._voice.available)
        hint = "  ^Space voice  ^E editor  F1 help" if has_voice else "  ^E editor  F1 help"

        yield Horizontal(
            Static("devsper", id="hd-logo"),
            Static("›", id="hd-sep"),
            Static(self.workspace.project_name, id="hd-proj"),
            Static(branch, id="hd-branch"),
            Static("", id="hd-fill"),
            Static("claude-sonnet", id="hd-model"),
            id="header",
        )
        yield VerticalScroll(id="conversation")
        yield Horizontal(
            Label("", id="status-left"),
            Label("🎤 recording…", id="status-voice"),
            id="status-bar",
        )
        yield Horizontal(
            Static("›", id="inp-prefix"),
            Input(placeholder="ask anything…", id="user-input"),
            Static(hint, id="inp-hint"),
            id="input-row",
        )
        yield Footer()

    def on_mount(self) -> None:
        if self._new_session:
            self.session.start_new_session()
        else:
            self.session.load_last_session()
        self._print_banner()
        self.query_one("#user-input", Input).focus()

        # Pre-compile Swift binary in background
        if self._voice and self._voice._dictation:
            threading.Thread(
                target=self._voice._dictation.ensure_compiled, daemon=True
            ).start()

    def on_unmount(self) -> None:
        self._kill_voice_proc()

    # ------------------------------------------------------------------
    # Banner
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        try:
            from devsper import __version__
            ver = __version__
        except Exception:
            ver = "?"

        has_md = self.workspace.md_content is not None
        n_facts = self._intelligence.fact_count() if self._intelligence else 0

        t = RichText()
        t.append("devsper", style="bold #7c6af7")
        t.append(f" v{ver}", style="#475569")
        t.append("  ·  ", style="#1e293b")
        t.append(self.workspace.project_name, style="bold #e2e8f0")
        self._mount_widget(Static(t, classes="msg-wrap"))

        if has_md:
            self._mount_widget(Static("[#22c55e]  ✓ devsper.md[/]", classes="msg-wrap"))
        else:
            self._mount_widget(Static("[#f59e0b]  ⚠ no devsper.md[/]  [#334155]→ /init[/]", classes="msg-wrap"))
        if n_facts:
            self._mount_widget(Static(f"[#334155]  {n_facts} memory facts[/]", classes="msg-wrap"))

        sep = RichText("─" * 60, style="#1a1d2e")
        self._mount_widget(Static(sep, classes="msg-wrap"))

    # ------------------------------------------------------------------
    # Input / submit
    # ------------------------------------------------------------------

    @on(Input.Submitted, "#user-input")
    def handle_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.clear()
        if not text or self._busy:
            return
        if text.startswith("/"):
            self._handle_slash(text)
        else:
            self._run_turn(text)

    # ------------------------------------------------------------------
    # Voice — Ctrl+Space toggle
    # ------------------------------------------------------------------

    def action_toggle_voice(self) -> None:
        if self._busy:
            return
        if self._recording:
            self._stop_recording()
        elif self._voice and self._voice.available:
            self._start_voice()
        else:
            self._set_status("voice unavailable")

    def action_cancel_voice(self) -> None:
        if self._recording:
            self._stop_recording()

    def _start_voice(self) -> None:
        self._recording = True
        self._set_voice_badge(True)
        self._set_status("recording — Ctrl+Space or Escape to stop")
        self.query_one("#user-input", Input).disabled = True

        def _record() -> None:
            try:
                text = self._voice._record(tui_mode=True)
            except Exception:
                text = ""
            self.post_message(_VoiceResult(text))

        threading.Thread(target=_record, daemon=True).start()

    def _stop_recording(self) -> None:
        """Send SIGTERM — recording thread's communicate() collects transcript."""
        self._kill_voice_proc()

    def _kill_voice_proc(self) -> None:
        try:
            if self._voice and self._voice._dictation:
                proc = self._voice._dictation._current_proc
                if proc and proc.poll() is None:
                    proc.terminate()
        except Exception:
            pass

    def on__voice_result(self, msg: _VoiceResult) -> None:
        self._recording = False
        self._set_voice_badge(False)
        self._set_status("")
        inp = self.query_one("#user-input", Input)
        inp.disabled = False
        if msg.text:
            inp.value = msg.text
            inp.cursor_position = len(msg.text)
        else:
            self._mount_widget(Static("[#475569]  nothing heard[/]", classes="msg-wrap"))
        inp.focus()

    def _set_voice_badge(self, active: bool) -> None:
        badge = self.query_one("#status-voice")
        if active:
            badge.add_class("active")
        else:
            badge.remove_class("active")

    # ------------------------------------------------------------------
    # Turn execution
    # ------------------------------------------------------------------

    def _run_turn(self, user_text: str) -> None:
        self._mount_widget(_user_widget(user_text))
        self.session.save_turn("user", user_text)
        self._set_busy(True)
        self._set_status("thinking…")
        self._mount_widget(_thinking_widget())
        self._execute_turn(user_text)

    @work(thread=True)
    def _execute_turn(self, user_text: str) -> None:
        from devsper.workspace.display import CallbackEventLog, format_event_line

        def _on_event(evt: dict) -> None:
            line = format_event_line(evt)
            if line:
                self.post_message(_AppendLine(f"  [#334155]● {line}[/]"))

        event_log = CallbackEventLog(callback=_on_event)
        swarm = self._make_swarm(event_log)
        task = self._build_task(user_text)
        try:
            result = swarm.run(task)
            answer = self._extract_answer(result)
        except Exception as exc:
            answer = f"**Error:** {exc}"
        self.post_message(_TurnDone(answer or ""))

    def on__turn_done(self, msg: _TurnDone) -> None:
        # Remove thinking indicator
        try:
            self.query_one("#thinking-indicator").remove()
        except Exception:
            pass

        if msg.answer:
            # Header line
            header = RichText()
            header.append("  ◆ devsper", style="bold #a78bfa")
            self._mount_widget(Static(header, classes="msg-wrap"))
            # Markdown body
            md_widget = Static(
                RichMarkdown(msg.answer, code_theme="monokai"),
                classes="msg-wrap",
            )
            self._mount_widget(md_widget)
            # Separator
            self._mount_widget(Static(RichText("─" * 60, style="#1a1d2e"), classes="msg-wrap"))

        self.session.save_turn("assistant", msg.answer)
        self._set_busy(False)
        self._set_status("")

        if self._intelligence and msg.answer:
            def _extract() -> None:
                try:
                    self._intelligence.extract_and_store("", msg.answer)
                except Exception:
                    pass
            threading.Thread(target=_extract, daemon=True).start()

    def on__append_line(self, msg: _AppendLine) -> None:
        self._mount_widget(Static(msg.text, classes="thinking-wrap"))

    def on__set_status(self, msg: _SetStatus) -> None:
        self._set_status(msg.text)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_quit(self) -> None:
        self._kill_voice_proc()
        self.session.close()
        self.exit()

    def action_new_session(self) -> None:
        sid = self.session.start_new_session()
        self._mount_widget(Static(f"[#22c55e]  ✓ new session {sid[:8]}[/]", classes="msg-wrap"))

    def action_clear_screen(self) -> None:
        conv = self.query_one("#conversation", VerticalScroll)
        conv.remove_children()
        self._print_banner()

    def action_show_help(self) -> None:
        help_md = RichMarkdown("""
**Commands**
| | |
|---|---|
| `/init [--force]` | generate devsper.md |
| `/new` | new session |
| `/sessions` | list sessions |
| `/memory [query]` | search memory |
| `/mission r2c <goal>` | research → code |
| `/council <task>` | draft → critique → synthesize |
| `/clear` | clear screen |
| `/help` | this message |

**Keys**
| | |
|---|---|
| `Ctrl+Space` | toggle voice recording |
| `Ctrl+E` | open in $EDITOR |
| `Ctrl+N` | new session |
| `Ctrl+L` | clear |
| `Escape` | cancel voice |
""")
        self._mount_widget(Static(help_md, classes="msg-wrap"))

    def action_edit_in_editor(self) -> None:
        inp = self.query_one("#user-input", Input)
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nvim"
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, prefix="devsper_") as f:
            f.write(inp.value)
            tmpfile = f.name
        try:
            with self.suspend():
                subprocess.run([editor, tmpfile], check=False)
            new_text = Path(tmpfile).read_text().rstrip("\n")
            inp.value = new_text
            inp.cursor_position = len(new_text)
        except Exception as exc:
            self._mount_widget(Static(f"[#ef4444]  editor error: {exc}[/]", classes="msg-wrap"))
        finally:
            Path(tmpfile).unlink(missing_ok=True)
        inp.focus()

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    def _handle_slash(self, text: str) -> None:
        parts = text.split(None, 1)
        cmd, arg = parts[0].lower(), (parts[1] if len(parts) > 1 else "")
        dispatch = {
            "/exit":     self.action_quit,
            "/quit":     self.action_quit,
            "/new":      self.action_new_session,
            "/sessions": self._show_sessions,
            "/memory":   lambda: self._query_memory(arg.strip()),
            "/init":     lambda: self._run_init(force="--force" in arg),
            "/mission":  lambda: self._run_mission(arg.strip()),
            "/council":  lambda: self._run_council(arg.strip()),
            "/help":     self.action_show_help,
            "/clear":    self.action_clear_screen,
        }
        fn = dispatch.get(cmd)
        if fn:
            fn()
        else:
            self._mount_widget(Static(f"[#475569]  unknown: {cmd}  →  /help[/]", classes="msg-wrap"))

    def _show_sessions(self) -> None:
        sessions = self.session.list_sessions()
        if not sessions:
            self._mount_widget(Static("[#475569]  no sessions[/]", classes="msg-wrap"))
            return
        active = self.session._session_id
        lines = ["[bold #7c6af7]  sessions[/]"]
        for s in sessions:
            mark = "  [#22c55e]← active[/]" if s["session_id"] == active else ""
            lines.append(f"  [#475569]{s['session_id'][:8]}[/]  {s['turn_count']} turns{mark}")
        self._mount_widget(Static("\n".join(lines), classes="msg-wrap"))

    def _query_memory(self, query: str) -> None:
        try:
            from devsper.memory.memory_store import get_default_store
            store = get_default_store()
            ns = f"project:{self.workspace.project_id}"
            results = (
                store.search(query, namespace=ns, top_k=5)
                if query else store.list(namespace=ns, limit=10)
            )
            if not results:
                self._mount_widget(Static("[#475569]  no memories[/]", classes="msg-wrap"))
            else:
                lines = ["[bold #7c6af7]  memory[/]"]
                for i, item in enumerate(results, 1):
                    txt = getattr(item, "text", None) or str(item)
                    lines.append(f"  [#475569]{i}.[/] {txt[:120]}")
                self._mount_widget(Static("\n".join(lines), classes="msg-wrap"))
        except Exception as exc:
            self._mount_widget(Static(f"[#ef4444]  memory unavailable: {exc}[/]", classes="msg-wrap"))

    def _run_init(self, force: bool = False) -> None:
        md_path = self.workspace.project_root / "devsper.md"
        if md_path.exists() and not force:
            self._mount_widget(Static(
                "[#f59e0b]  devsper.md exists[/]  [#334155]→ /init --force to regenerate[/]",
                classes="msg-wrap",
            ))
            return
        self._mount_widget(Static("[#475569]  generating devsper.md…[/]", classes="msg-wrap"))
        self._set_busy(True)

        def _do() -> None:
            try:
                from devsper.cli.init import run_init_md
                rc = run_init_md(self.workspace.project_root, overwrite=force)
                self.post_message(_AppendLine("[#22c55e]  ✓ devsper.md ready[/]" if rc == 0 else "[#ef4444]  init failed[/]"))
            except Exception as exc:
                self.post_message(_AppendLine(f"[#ef4444]  init error: {exc}[/]"))
            self.post_message(_TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    def _run_mission(self, arg: str) -> None:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            self._mount_widget(Static("[#475569]  usage: /mission r2c <goal>[/]", classes="msg-wrap"))
            return
        _, goal = parts[0].lower(), parts[1]
        self._set_busy(True)

        def _do() -> None:
            try:
                from devsper.council.research_to_code import ResearchToCodeMission
                result = ResearchToCodeMission().run(goal)
                self.post_message(_AppendLine(f"[#7c6af7]  summary:[/] {result.handoff.summary}"))
                self.post_message(_TurnDone(result.final_code))
            except Exception as exc:
                self.post_message(_AppendLine(f"[#ef4444]  mission failed: {exc}[/]"))
                self.post_message(_TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    def _run_council(self, task: str) -> None:
        if not task:
            self._mount_widget(Static("[#475569]  usage: /council <task>[/]", classes="msg-wrap"))
            return
        self._set_busy(True)

        def _do() -> None:
            try:
                from devsper.council import Council, CouncilConfig
                result = Council(CouncilConfig()).run(task)
                self.post_message(_TurnDone(result.final))
            except Exception as exc:
                self.post_message(_AppendLine(f"[#ef4444]  council failed: {exc}[/]"))
                self.post_message(_TurnDone(""))

        threading.Thread(target=_do, daemon=True).start()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mount_widget(self, widget: Static) -> None:
        conv = self.query_one("#conversation", VerticalScroll)
        conv.mount(widget)
        self.call_after_refresh(conv.scroll_end, animate=False)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.query_one("#user-input", Input).disabled = busy

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#status-left", Label).update(f"  {text}" if text else "")
        except Exception:
            pass

    def _git_branch(self) -> str:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace.project_root,
                capture_output=True, text=True, timeout=2,
            )
            b = r.stdout.strip()
            return f"  {b}" if b and b != "HEAD" else ""
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
        try:
            cfg = copy.deepcopy(get_config())
            if hasattr(cfg, "agents") and hasattr(cfg.agents, "identity"):
                cfg.agents.identity.memory_namespace = f"project:{self.workspace.project_id}"
            return Swarm(event_log=event_log, config=cfg)
        except Exception:
            return Swarm(event_log=event_log, worker_model="auto", planner_model="auto", use_tools=True, adaptive=True)

    def _extract_answer(self, result) -> str:
        if not isinstance(result, dict):
            return str(result)
        for key in ("answer", "result", "output", "summary", "response"):
            val = result.get(key)
            if val and isinstance(val, str):
                return val
        return "\n\n".join(v.strip() for v in result.values() if isinstance(v, str) and v.strip())
