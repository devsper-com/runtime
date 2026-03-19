"""
devsper CLI theme: sharp, dark-terminal-native, information-dense.
All CLI code imports console from here, never from rich directly.
"""

import sys

from rich.theme import Theme
from rich.console import Console

THEME = Theme({
    # New branding namespace (preferred)
    "devsper.primary": "#F5A623",      # amber — brand, headers, highlights
    "devsper.secondary": "#4A9EFF",    # electric blue — info, links, tool names
    "devsper.success": "#3DDC84",      # green — completed, healthy
    "devsper.warning": "#FFD166",      # yellow — warnings, SLA at risk
    "devsper.error": "#FF4757",        # red — failures, errors
    "devsper.muted": "#6B7280",        # gray — timestamps, secondary info
    "devsper.dim": "#374151",          # dark gray — borders, dividers
    "devsper.agent": "#A78BFA",        # purple — agent activity
    "devsper.tool": "#34D399",         # teal — tool calls
    "devsper.planner": "#FB923C",      # orange — planner activity
    "devsper.cost": "#F472B6",         # pink — cost/token info

    # Back-compat aliases (old "hive.*" keys)
    "hive.primary": "#F5A623",      # amber — brand, headers, highlights
    "hive.secondary": "#4A9EFF",    # electric blue — info, links, tool names
    "hive.success": "#3DDC84",      # green — completed, healthy
    "hive.warning": "#FFD166",       # yellow — warnings, SLA at risk
    "hive.error": "#FF4757",         # red — failures, errors
    "hive.muted": "#6B7280",         # gray — timestamps, secondary info
    "hive.dim": "#374151",           # dark gray — borders, dividers
    "hive.agent": "#A78BFA",         # purple — agent activity
    "hive.tool": "#34D399",          # teal — tool calls
    "hive.planner": "#FB923C",       # orange — planner activity
    "hive.cost": "#F472B6",          # pink — cost/token info
})

# Respect NO_COLOR and --no-color (set by main before first use)
def _make_console(**kwargs: object) -> Console:
    # NOTE: in Cursor/PTY and some CI-ish wrappers, isatty() can be false even though
    # Rich Live is expected to render in-place. Force terminal mode so Live updates
    # don't print stacked frames.
    return Console(theme=THEME, highlight=False, force_terminal=True, **kwargs)

# Single shared Console for the entire process.
# Rich Live must share the same Console as all other printing to avoid orphan output.
console = _make_console()
err_console = console


class ThemeStyle:
    """Convenience names for theme styles (e.g. ClarificationWidget)."""
    amber = "devsper.primary"
    dim = "devsper.dim"


def reconfigure_console(no_color: bool = False, force_terminal: bool | None = None) -> None:
    """Reconfigure global consoles (e.g. for --no-color, --plain)."""
    global console, err_console
    kw: dict = {"theme": THEME, "highlight": False}
    if no_color:
        kw["no_color"] = True
    if force_terminal is not None:
        kw["force_terminal"] = force_terminal
    console = Console(**kw)
    err_console = console
