"""
devsper CLI theme: sharp, dark-terminal-native, information-dense.
All CLI code imports console from here, never from rich directly.
"""

from rich.theme import Theme
from rich.console import Console

THEME = Theme({
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
    return Console(theme=THEME, highlight=False, **kwargs)

console = _make_console()
err_console = _make_console(stderr=True)


def reconfigure_console(no_color: bool = False, force_terminal: bool | None = None) -> None:
    """Reconfigure global consoles (e.g. for --no-color, --plain)."""
    global console, err_console
    kw: dict = {"theme": THEME, "highlight": False}
    if no_color:
        kw["no_color"] = True
    if force_terminal is not None:
        kw["force_terminal"] = force_terminal
    console = Console(**kw)
    err_console = Console(stderr=True, **kw)
