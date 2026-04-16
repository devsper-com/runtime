"""Thin CLI wrapper — finds and execs the Rust devsper binary."""
from __future__ import annotations

import os
import sys
import shutil
import pathlib

import click


def find_binary() -> str:
    """Find the devsper Rust binary.

    Search order:
    1. devsper-runtime on PATH (installed wheel)
    2. devsper on PATH
    3. Alongside this package (bundled wheel)
    4. Cargo build output (dev mode)
    """
    for name in ("devsper-runtime", "devsper"):
        binary = shutil.which(name)
        if binary and _is_rust_binary(binary):
            return binary

    pkg_dir = pathlib.Path(__file__).parent
    repo_root = pkg_dir.parent.parent

    candidates = [
        pkg_dir / "bin" / "devsper",
        pkg_dir / "bin" / "devsper.exe",
        repo_root / "target" / "release" / "devsper",
        repo_root / "target" / "debug" / "devsper",
    ]
    for c in candidates:
        if c.exists() and os.access(c, os.X_OK):
            return str(c)

    click.echo(
        "Error: devsper Rust binary not found.\n"
        "\n"
        "Build with:   cargo build --release -p devsper-bin\n"
        "Or install:   pip install devsper[runtime]\n",
        err=True,
    )
    sys.exit(1)


def _is_rust_binary(path: str) -> bool:
    """Heuristic: not this Python script."""
    return not path.endswith(".py")


@click.group(invoke_without_command=True, context_settings={"ignore_unknown_options": True})
@click.pass_context
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def main(ctx: click.Context, args: tuple) -> None:
    """Devsper — self-evolving AI workflow engine.

    \b
    Commands are passed directly to the Rust runtime:
      devsper run workflow.devsper
      devsper compile workflow.devsper
      devsper peer --listen 0.0.0.0:7000
      devsper inspect <run-id>

    \b
    Interactive UI:
      devsper tui
    """
    if ctx.invoked_subcommand is not None:
        return

    if args and args[0] == "tui":
        _launch_tui(list(args[1:]))
        return

    # Pass-through to Rust binary
    binary = find_binary()
    os.execv(binary, [binary] + list(args))


@main.command(name="tui")
@click.argument("run_id", required=False, default=None)
def tui_command(run_id: str | None) -> None:
    """Launch the interactive TUI (requires 'devsper[tui]' extras)."""
    extra_args = ["--run-id", run_id] if run_id else []
    _launch_tui(extra_args)


def _launch_tui(args: list[str]) -> None:
    """Start the Textual TUI application."""
    try:
        from devsper.tui.app import DevSperApp  # noqa: PLC0415
    except ImportError:
        click.echo(
            "TUI requires optional dependencies:\n"
            "  pip install 'devsper[tui]'\n",
            err=True,
        )
        sys.exit(1)

    app = DevSperApp(extra_args=args)
    app.run()
