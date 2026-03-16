"""
Startup nag: print upgrade notice if behind, once per session; suppress during upgrade.
"""

import time

from rich.console import Console
from rich.panel import Panel

_notified = False
_suppress = False
_console = Console(stderr=True)


def suppress_notifications() -> None:
    """Call when running 'devsper upgrade' so the nag does not appear."""
    global _suppress
    _suppress = True


def check_and_notify() -> None:
    """
    If an update is available, print a compact Rich notice once per session.
    Non-blocking, try/except, aim for <100ms (cache read usually).
    """
    global _notified
    if _suppress or _notified:
        return
    deadline = time.monotonic() + 0.1  # 100ms max
    try:
        from .version_check import is_update_available, get_version_diff_type

        if time.monotonic() > deadline:
            return
        available, current, latest = is_update_available()
        if not available or current == latest:
            return
        if time.monotonic() > deadline:
            return
        _notified = True
        diff_type = get_version_diff_type(current, latest)
        color: str = {"major": "red", "minor": "yellow", "patch": "green"}.get(
            diff_type, "white"
        )
        msg = (
            f"Update available: [bold]{current}[/bold] → [bold]{latest}[/bold]  "
            f"[{color}][{diff_type}][/{color}]\n"
            "Run [bold]devsper upgrade[/bold] to update"
        )
        _console.print(Panel(msg, border_style="dim", padding=(0, 1)))
    except Exception:
        pass
