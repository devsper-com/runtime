"""
devsper upgrade subcommand: version check, changelog, installer detection, install, verify.
"""

import sys
from typing import Literal

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm
from rich.spinner import Spinner
from .version_check import (
    get_current_version,
    get_latest_version,
    is_update_available,
    get_version_diff_type,
)
from .changelog import fetch_changelog, parse_changelog, get_changes_between, format_changelog_rich
from .installer import detect_installer, get_install_command, perform_install, verify_installation
from .notifier import suppress_notifications

_console = Console(stderr=True)
PACKAGE = "devsper"


def _diff_type_color(t: Literal["major", "minor", "patch"]) -> str:
    return {"major": "red", "minor": "yellow", "patch": "green"}.get(t, "white")


def run_upgrade(args: object) -> int:
    """
    Entry point for 'devsper upgrade'.
    Supports: --check, --yes/-y, --version VERSION, --dry-run.
    """
    # Avoid startup nag during upgrade
    suppress_notifications()

    check_only = getattr(args, "check", False)
    yes = getattr(args, "yes", False)
    version_override = getattr(args, "version", None)
    dry_run = getattr(args, "dry_run", False)

    current = get_current_version()

    # ---- Step 1: Version check ----
    if version_override:
        latest = version_override
        from .version_check import parse_semver
        cur_t = parse_semver(current)
        lat_t = parse_semver(latest)
        available = lat_t > cur_t
        _console.print(f"[dim]Installing specified version {latest}[/dim]")
    else:
        _console.print("[dim]Fetching latest version from PyPI...[/dim]")
        try:
            available, _, latest = is_update_available()
        except Exception as e:
            _console.print(f"[red]Error checking PyPI: {e}[/red]")
            return 1

    diff_type = get_version_diff_type(current, latest)
    color = _diff_type_color(diff_type)
    _console.print(f"{PACKAGE} [bold]{current}[/bold] → [bold]{latest}[/bold]  [{color}][{diff_type} update][/{color}]")

    if check_only:
        if not available and not version_override:
            _console.print("[green]You are on the latest version.[/green]")
        return 0

    if not available and not version_override:
        _console.print("[green]Already on latest version. Use --version X.Y.Z to install a specific version.[/green]")
        return 0

    # Specific version check: ensure it exists on PyPI (optional: could add a quick PyPI check)
    if version_override:
        # We'll discover "not found" during install
        pass

    # ---- Step 2: Changelog ----
    changelog_raw = fetch_changelog()
    changes: list[dict] = []
    if changelog_raw:
        parsed = parse_changelog(changelog_raw)
        changes = get_changes_between(parsed, current, latest)
        if changes:
            if len(changes) > 3:
                _console.print(f"[dim]Showing changes across {len(changes)} releases[/dim]")
            formatted = format_changelog_rich(changes)
            _console.print(Panel(formatted, title="Changelog", border_style="blue"))
    else:
        _console.print("[dim]Changelog unavailable (network or repo).[/dim]")

    # ---- Step 3: Installer detection ----
    installer = detect_installer()
    if installer == "uv":
        _console.print("  [green]Installing with uv[/green] ✓")
        _console.print("  [dim]uv detected in environment[/dim]")
    else:
        _console.print("  Installing with [yellow]pip[/yellow]")

    if dry_run:
        cmd = get_install_command(installer, version=latest)
        _console.print(f"[dim]Dry run: would run: {' '.join(cmd)}[/dim]")
        return 0

    # ---- Step 4: Confirmation ----
    if not yes:
        proceed = Confirm.ask("Proceed with upgrade?", default=True, console=_console)
        if not proceed:
            _console.print("Cancelled.")
            return 0

    # ---- Step 5: Installation with progress ----
    with Live(
        Spinner("dots", text=f"  Installing {PACKAGE} {latest}..."),
        console=_console,
        refresh_per_second=10,
    ):
        success, output = perform_install(installer, version=latest)

    if not success:
        _console.print("[red]Installation failed:[/red]")
        _console.print(output)
        _console.print("[dim]Try running with --verbose or use pip/uv directly.[/dim]")
        if "Permission denied" in output or "permission" in output.lower():
            _console.print("[yellow]Tip: use a virtualenv or run with appropriate permissions.[/yellow]")
        if "404" in output or "not found" in output.lower():
            _console.print(f"[yellow]Version {latest} may not exist on PyPI.[/yellow]")
        return 1

    # ---- Step 6: Verification ----
    if verify_installation(latest):
        _console.print(f"  [green]✓ Successfully upgraded to {PACKAGE} {latest}[/green]")
    else:
        _console.print(f"  [yellow]Upgrade completed but version check failed. Run [bold]devsper --version[/bold] to confirm.[/yellow]")

    # ---- Step 7: Post-install summary ----
    if diff_type == "major":
        _console.print("  [bold red]⚠ Major update — review breaking changes above[/bold red]")
    _console.print("  [dim]Run devsper --help to see commands[/dim]")
    if changes:
        _console.print(f"  [dim]{len(changes)} release(s) applied.[/dim]")

    return 0
