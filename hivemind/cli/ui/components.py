"""
Reusable Rich renderables for CLI. All CLI code imports from here, not rich directly.
"""

from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from hivemind.cli.ui.theme import console

# Status badge styles
BADGE_STYLES = {
    "SUCCESS": "hive.success",
    "FAILED": "hive.error",
    "RUNNING": "hive.secondary",
    "SKIPPED": "hive.muted",
    "CACHED": "hive.primary",
    "PENDING": "hive.dim",
}


def HivemindHeader(
    version: str = "",
    model: str = "",
    workers: int = 0,
) -> Text:
    """Single-line wordmark + version. Example: ⬡ hivemind  v2.1.5  ·  claude-sonnet-4  ·  4 workers"""
    parts = [Text("⬡ hivemind", style="hive.primary")]
    if version:
        parts.append(Text(f"  v{version}", style="hive.muted"))
    if model:
        parts.append(Text(f"  ·  {model}", style="hive.muted"))
    if workers:
        parts.append(Text(f"  ·  {workers} workers", style="hive.muted"))
    out = Text()
    for p in parts:
        out.append_text(p)
    return out


def StatusBadge(text: str, style: str | None = None) -> Text:
    """Inline colored badge: [SUCCESS], [FAILED], [RUNNING], etc."""
    key = text.upper().replace(" ", "_")
    s = style or BADGE_STYLES.get(key, "hive.muted")
    return Text(f"[{text}]", style=s)


def TaskRow(
    short_id: str,
    description: str,
    role: str = "",
    duration: str = "—",
    status: str = "pending",
    icon: str | None = None,
) -> Text:
    """Single-line task summary. status: pending|running|completed|failed|cached|skipped."""
    if icon is None:
        icon = {"pending": "○", "running": "◐", "completed": "✓", "failed": "✗", "cached": "⚡", "skipped": "⊘"}.get(status, "○")
    style = {"completed": "hive.success", "failed": "hive.error", "cached": "hive.primary", "skipped": "hive.muted", "running": "hive.secondary", "pending": "hive.dim"}.get(status, "hive.dim")
    desc = (description or "")[:45]
    if len((description or "")) > 45:
        desc = desc.rstrip() + "…"
    role_part = f"  {role}" if role else ""
    return Text().append(icon + " ", style=style).append(short_id + "  ", style="hive.secondary").append(desc, style="dim").append(role_part, style="hive.muted").append("  ", style="").append(duration, style="hive.muted")


def RoleTag(role: str) -> Text:
    """Colored inline tag per role: research->blue, code->teal, analysis->purple, critic->orange, architect->amber."""
    styles = {"research": "hive.secondary", "code": "hive.tool", "analysis": "hive.agent", "critic": "hive.planner", "architect": "hive.primary"}
    s = styles.get((role or "").lower(), "hive.muted")
    return Text(role or "—", style=s)


def CostDisplay(usd: float | None) -> Text:
    """$0.0034 in pink, '—' in muted if None."""
    if usd is None:
        return Text("—", style="hive.muted")
    return Text(f"${usd:.4f}", style="hive.cost")


def SectionHeader(title: str) -> Rule:
    """Amber rule with title."""
    return Rule(title, style="hive.primary", characters="─")


def ErrorPanel(message: str, hint: str | None = None, docs_url: str | None = None) -> Panel:
    """Red-bordered panel, title 'Error'. No tracebacks to end users."""
    body = message
    if hint:
        body += "\n\n" + f"Hint: {hint}"
    if docs_url:
        body += "\n" + f"Docs: {docs_url}"
    return Panel(body, title="Error", border_style="hive.error")
