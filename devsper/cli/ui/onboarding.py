"""
Init wizard: welcome screen, provider setup, model selection, workers, features, write config.
Uses theme and components; --no-interactive writes minimal config and prints next steps.
"""

import os
import sys
from pathlib import Path

from rich.panel import Panel
from rich.text import Text

from devsper.cli.ui.theme import console


DOCS_URL = "https://docs.devsper.com"
GITHUB_URL = "https://github.com/devsper-com/runtime"


def _wordmark_ascii() -> str:
    """6-line block letters 'devsper' in ASCII. Fallback if pyfiglet missing."""
    try:
        import pyfiglet
        return pyfiglet.figlet_format("devsper", font="standard").rstrip()
    except ImportError:
        return """
 _   _ _   _ __  __ _____  __  __ ___  _   _ ____
| | | | | | |  \\/  | ____| |  \\/  | _ \\| \\ | |  _ \\
| |_| | | | | |\\/| |  _|   | |\\/| | | | |  \\| | | | |
|  _  | |_| | |  | | |___  | |  | | |_| | |\\  | |_| |
|_| |_|\\___/|_|  |_|_____| |_|  |_|___/|_| \\_|____/
""".strip()


class InitWizard:
    """Interactive init: welcome, providers, models, workers, features, write config."""

    def __init__(self, cwd: Path | None = None) -> None:
        self.cwd = cwd or Path.cwd()

    def run(self, no_interactive: bool = False) -> int:
        """Run full wizard or minimal write when no_interactive."""
        if no_interactive:
            return self._run_minimal()
        return self._run_interactive()

    def _run_minimal(self) -> int:
        """Write minimal devsper.toml and print next steps."""
        from devsper.cli.init import _build_init_toml
        toml = _build_init_toml(workers=4, planner="auto", worker="auto")
        path = self.cwd / "devsper.toml"
        path.write_text(toml, encoding="utf-8")
        console.print("[hive.success]✓[/] Wrote [cyan]devsper.toml[/]")
        console.print()
        console.print("Next steps:")
        console.print("  1) Set API keys: [cyan]devsper credentials set <provider> api_key[/]")
        console.print("  2) Run: [cyan]devsper run \"your task\"[/]")
        console.print(f"  Docs: [link={DOCS_URL}]{DOCS_URL}[/]")
        return 0

    def _run_interactive(self) -> int:
        """Step 1: Welcome. Then delegate to existing init flow."""
        # Step 1 — Welcome
        console.clear()
        wordmark = _wordmark_ascii()
        console.print(Text(wordmark, style="hive.primary"))
        console.print()
        console.print("Welcome to devsper — distributed AI swarm runtime", style="hive.muted")
        try:
            import devsper
            ver = getattr(devsper, "__version__", "?")
            console.print(f"v{ver}  ·  [link={DOCS_URL}]{DOCS_URL}[/]  ·  [link={GITHUB_URL}]{GITHUB_URL}[/]", style="hive.muted")
        except Exception:
            console.print(f"[link={DOCS_URL}]{DOCS_URL}[/]  ·  [link={GITHUB_URL}]{GITHUB_URL}[/]", style="hive.muted")
        console.print()
        try:
            from rich.prompt import Prompt
            Prompt.ask("[dim]Press Enter to continue[/]", default="")
        except Exception:
            input("Press Enter to continue...")
        # Delegate to existing init (writes toml and .env)
        from devsper.cli.init import _run_init_interactive, _write_env_file
        toml_content, api_keys = _run_init_interactive(self.cwd)
        path = self.cwd / "devsper.toml"
        path.write_text(toml_content, encoding="utf-8")
        if api_keys:
            _write_env_file(self.cwd, api_keys)
        console.print()
        console.print(Panel(
            "Try it:  [cyan]devsper run \"research quantum computing breakthroughs\"[/]\n\n"
            f"Docs:    {DOCS_URL}\n"
            "Discord: https://discord.gg/devsper",
            title="You're all set",
            border_style="hive.success",
        ))
        return 0


def run_init_wizard(no_interactive: bool = False, cwd: Path | None = None) -> int:
    """Entry point for devsper init."""
    wizard = InitWizard(cwd=cwd)
    return wizard.run(no_interactive=no_interactive)
