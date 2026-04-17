"""Thin CLI wrapper — finds and execs the Rust devsper binary."""
from __future__ import annotations

import json
import os
import sys
import shutil
import pathlib
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from devsper.credentials.inject import inject_credentials
from devsper.credentials import providers as cred_providers
from devsper.credentials import store as cred_store
from devsper.auth import github as github_auth

console = Console()


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
    inject_credentials()
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


# ---------------------------------------------------------------------------
# credentials group
# ---------------------------------------------------------------------------


@main.group()
def credentials() -> None:
    """Manage provider credentials stored in system keyring."""


@credentials.command("set")
@click.argument("provider", type=click.Choice(list(cred_providers.PROVIDERS.keys())))
def credentials_set(provider: str) -> None:
    """Store credentials for a provider in the system keyring."""
    p = cred_providers.PROVIDERS[provider]
    console.print(f"\n[bold]Configure {p.display_name}[/bold]\n")

    for f in p.fields:
        label = f.display_name
        if f.optional:
            default_hint = f.default or ""
            label = f"{label} (optional, default: {default_hint})" if default_hint else f"{label} (optional)"

        if f.secret:
            value = click.prompt(label, hide_input=True, default="", show_default=False).strip()
        else:
            value = click.prompt(label, default=f.default or "", show_default=bool(f.default)).strip()

        if value:
            cred_store.set(provider, f.name, value)
        elif f.optional and f.default:
            # Don't store the default — inject.py handles defaults at runtime
            pass

    console.print(f"\n[green]Credentials for [bold]{p.display_name}[/bold] saved.[/green]\n")


@credentials.command("list")
def credentials_list() -> None:
    """Show configured providers."""
    table = Table(title="Configured Providers", show_lines=True)
    table.add_column("Provider", style="bold")
    table.add_column("Status")
    table.add_column("Fields configured")

    for provider_name, provider in cred_providers.PROVIDERS.items():
        field_statuses: list[str] = []
        any_configured = False

        for f in provider.fields:
            env_val = os.environ.get(f.env_var) if f.env_var else None
            keyring_val = cred_store.get(provider_name, f.name)

            if env_val:
                display = "[green]set[/green] (env)"
                any_configured = True
            elif keyring_val:
                display = "[green]set[/green] (keyring)"
                any_configured = True
            elif f.default:
                display = f"[dim]default ({f.default})[/dim]"
            else:
                display = "[dim]not set[/dim]"

            field_statuses.append(f"{f.display_name}: {display}")

        status = "[green]configured[/green]" if any_configured else "[dim]not configured[/dim]"
        table.add_row(provider.display_name, status, "\n".join(field_statuses))

    console.print(table)


@credentials.command("remove")
@click.argument("provider", type=click.Choice(list(cred_providers.PROVIDERS.keys())))
def credentials_remove(provider: str) -> None:
    """Remove stored credentials for a provider."""
    p = cred_providers.PROVIDERS[provider]
    if not click.confirm(f"Remove all stored credentials for {p.display_name}?"):
        console.print("[dim]Aborted.[/dim]")
        return

    for f in p.fields:
        cred_store.delete(provider, f.name)

    console.print(f"[green]Credentials for [bold]{p.display_name}[/bold] removed.[/green]")


# ---------------------------------------------------------------------------
# auth group
# ---------------------------------------------------------------------------


@main.group()
def auth() -> None:
    """Authentication commands."""


@auth.command("github")
def auth_github() -> None:
    """Login to GitHub via device flow to use GitHub Models."""
    token = github_auth.login()
    cred_store.set("github", "token", token)
    console.print("\n[green]GitHub authentication successful. Token stored in keyring.[/green]\n")


@auth.command("status")
def auth_status() -> None:
    """Show authentication status for all providers."""
    table = Table(title="Authentication Status", show_lines=True)
    table.add_column("Provider", style="bold")
    table.add_column("Authenticated")
    table.add_column("Source")

    for provider_name, provider in cred_providers.PROVIDERS.items():
        authenticated = False
        source = ""

        for f in provider.fields:
            if f.env_var and os.environ.get(f.env_var):
                authenticated = True
                source = "env"
                break
            if cred_store.get(provider_name, f.name):
                authenticated = True
                source = "keyring"
                break

        auth_cell = "[green]yes[/green]" if authenticated else "[dim]no[/dim]"
        source_cell = source if authenticated else ""
        table.add_row(provider.display_name, auth_cell, source_cell)

    console.print(table)


# ---------------------------------------------------------------------------
# eval group
# ---------------------------------------------------------------------------


@main.group()
def eval() -> None:
    """Evaluate workflows against datasets."""


@eval.command("run")
@click.argument("workflow", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--dataset", "-d",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="JSONL dataset file",
)
@click.option(
    "--metrics", "-m",
    default="",
    help="Comma-separated metrics: relevance,correctness,groundedness",
)
@click.option(
    "--output", "-o",
    default="eval_results.jsonl",
    type=click.Path(),
    help="Output JSONL path",
)
@click.option(
    "--score/--no-score",
    default=True,
    help="Run LLM-as-judge scoring (requires devsper[eval])",
)
def eval_run(workflow: Path, dataset: Path, metrics: str, output: str, score: bool) -> None:
    """Run a workflow against a dataset and score outputs."""
    from devsper.eval.runner import load_dataset, run_case, save_results  # noqa: PLC0415

    binary = find_binary()
    inject_credentials()
    cases = load_dataset(dataset)

    console.print(f"\n[bold]Running {len(cases)} eval cases...[/bold]\n")

    results: list[dict] = []
    with console.status("Running cases...") as status:
        for i, case in enumerate(cases, 1):
            status.update(f"Case {i}/{len(cases)}")
            inputs = case.get("inputs", {"query": case.get("input", "")})
            r = run_case(binary, workflow, inputs)
            if "expected" in case:
                r["expected"] = case["expected"]
            results.append(r)
            icon = "[green]✓[/green]" if r["success"] else "[red]✗[/red]"
            console.print(f"  {icon} Case {i}: {r['latency_ms']}ms")

    if score and metrics:
        metric_list = [m.strip() for m in metrics.split(",") if m.strip()]
        console.print(f"\n[bold]Scoring with: {', '.join(metric_list)}[/bold]")
        try:
            from devsper.eval.scoring import score_results  # noqa: PLC0415
            results = score_results(results, metric_list)
        except ImportError as e:
            console.print(f"[yellow]Scoring skipped: {e}[/yellow]")

    save_results(results, Path(output))

    passed = sum(1 for r in results if r["success"])
    console.print(f"\n[bold]Results:[/bold] {passed}/{len(results)} passed → {output}\n")


@eval.command("report")
@click.option(
    "--input", "-i",
    "input_file",
    default="eval_results.jsonl",
    type=click.Path(exists=True),
)
@click.option("--last", default=0, help="Show last N results only")
def eval_report(input_file: str, last: int) -> None:
    """Show eval results as a table."""
    results: list[dict] = []
    with open(input_file) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))

    if last:
        results = results[-last:]

    table = Table(title=f"Eval Results: {input_file}", show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("Status")
    table.add_column("Input")
    table.add_column("Latency")
    table.add_column("Scores")

    for i, r in enumerate(results, 1):
        status = "[green]pass[/green]" if r.get("success") else "[red]fail[/red]"
        inputs = r.get("inputs", {})
        input_str = list(inputs.values())[0][:60] if inputs else ""
        latency = f"{r.get('latency_ms', 0)}ms"
        scores = r.get("scores", {})
        score_str = (
            ", ".join(f"{k}: {v:.2f}" for k, v in scores.items()) if scores else "-"
        )
        table.add_row(str(i), status, input_str, latency, score_str)

    console.print(table)
