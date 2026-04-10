"""Rich-based display for the coding REPL — tool call lines and diffs."""

from __future__ import annotations

import json
import re
from typing import Callable

from devsper.utils.event_logger import EventLog


# ---------------------------------------------------------------------------
# Event formatting
# ---------------------------------------------------------------------------

def format_event_line(event: dict) -> str | None:
    """Convert a swarm event dict to a one-line display string, or None to suppress."""
    event_type = event.get("type", "")

    if event_type == "tool_start":
        tool = event.get("tool", "tool")
        args = event.get("args", {})
        detail = _first_meaningful_arg(args)
        return f"  [bold cyan]●[/] [dim]{tool}[/] {detail}..." if detail else f"  [bold cyan]●[/] [dim]{tool}[/]..."

    if event_type == "tool_done":
        tool = event.get("tool", "tool")
        result = event.get("result", {})
        detail = _summarize_result(result)
        return f"  [green]●[/] [dim]{tool}[/] {detail}" if detail else f"  [green]●[/] [dim]{tool}[/]"

    if event_type == "agent_start":
        role = event.get("role") or event.get("agent_role", "agent")
        desc = event.get("description", "")
        short = desc[:60] + "..." if len(desc) > 60 else desc
        return f"  [bold magenta]◎[/] [dim]Agent ({role})[/] {short}"

    if event_type == "agent_done":
        role = event.get("role") or event.get("agent_role", "agent")
        return f"  [green]◎[/] [dim]Agent ({role}) done[/]"

    # Suppress everything else
    return None


def format_diff_block(diff_str: str, file_path: str) -> str:
    """Return a Rich markup string for a unified diff.

    Content is escaped before wrapping in markup tags to prevent diff lines
    containing Rich markup syntax (e.g. ``[bold]``) from corrupting output.
    """
    try:
        from rich.markup import escape as _escape
    except ImportError:
        _escape = lambda s: s  # noqa: E731

    if not diff_str.strip():
        return ""
    lines = []
    lines.append(f"  [bold]Editing[/] [cyan]{_escape(file_path)}[/]")
    for line in diff_str.splitlines():
        safe = _escape(line)
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(f"  [green]{safe}[/]")
        elif line.startswith("-") and not line.startswith("---"):
            lines.append(f"  [red]{safe}[/]")
        elif line.startswith("@@"):
            lines.append(f"  [bold yellow]{safe}[/]")
        else:
            lines.append(f"  {safe}")
    return "\n".join(lines)


def _first_meaningful_arg(args: dict) -> str:
    """Pull the most informative arg value for display."""
    for key in ("file", "path", "query", "pattern", "command", "url", "name"):
        if key in args:
            val = str(args[key])
            return val[:50] + "..." if len(val) > 50 else val
    vals = list(args.values())
    if vals:
        val = str(vals[0])
        return val[:50] + "..." if len(val) > 50 else val
    return ""


def _summarize_result(result: dict | str) -> str:
    if not isinstance(result, dict):
        return ""
    lines = result.get("lines", result.get("line_count", ""))
    if lines:
        return f"({lines} lines)"
    matches = result.get("matches", result.get("count", ""))
    if matches:
        return f"({matches} matches)"
    added = result.get("lines_added")
    removed = result.get("lines_removed")
    if added is not None:
        return f"+{added} -{removed}"
    return ""


# ---------------------------------------------------------------------------
# CallbackEventLog
# ---------------------------------------------------------------------------

class CallbackEventLog(EventLog):
    """EventLog subclass that calls a callback on every appended event.

    Usage::

        def on_event(event_dict: dict) -> None:
            line = format_event_line(event_dict)
            if line:
                console.print(line)

        event_log = CallbackEventLog(callback=on_event, events_folder_path="/tmp/devsper-events")
        swarm = Swarm(event_log=event_log)
    """

    def __init__(self, callback: Callable[[dict], None], **kwargs) -> None:
        super().__init__(**kwargs)
        self._callback = callback

    def append_event(self, event) -> None:  # type: ignore[override]  # intentionally widened
        try:
            super().append_event(event)
        except Exception:
            pass  # Never let log errors block the callback
        try:
            if hasattr(event, "model_dump"):
                event_dict = event.model_dump()
            elif hasattr(event, "__dict__"):
                event_dict = event.__dict__.copy()
            else:
                event_dict = {}
            self._callback(event_dict)
        except Exception:
            pass  # Never let display errors kill the swarm


# ---------------------------------------------------------------------------
# ToolCallDisplay  (stateful Rich renderer for the REPL)
# ---------------------------------------------------------------------------

class ToolCallDisplay:
    """Renders tool-call events to the terminal using Rich."""

    def __init__(self, console=None) -> None:
        try:
            from rich.console import Console
            self._console = console or Console()
        except ImportError:
            self._console = None

    def on_event(self, event_dict: dict) -> None:
        """Receive an event dict from CallbackEventLog and render it."""
        # Special handling for str_replace_file results (show diff inline)
        if event_dict.get("type") == "tool_done" and event_dict.get("tool") == "str_replace_file":
            raw_result = event_dict.get("result", {})
            if isinstance(raw_result, str):
                try:
                    raw_result = json.loads(raw_result)
                except Exception:
                    pass
            diff = raw_result.get("diff", "") if isinstance(raw_result, dict) else ""
            file_path = raw_result.get("file", "") if isinstance(raw_result, dict) else ""
            if diff and self._console:
                self._console.print(format_diff_block(diff, file_path), markup=True)
            return

        line = format_event_line(event_dict)
        if line and self._console:
            self._console.print(line, markup=True)
        elif line:
            print(re.sub(r"\[/?[^\]]*\]", "", line))
