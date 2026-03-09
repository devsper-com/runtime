"""
Rich CLI output for RunReport.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hivemind.types.task import TaskStatus
from hivemind.intelligence.analysis.run_report import RunReport
from hivemind.intelligence.analysis.cost_estimator import CostEstimator


def print_run_report(report: RunReport, console: Console) -> None:
    """Print report sections: header, overview, timeline table, critical path, tool usage, analysis panel, footer."""
    # 1. Header
    console.print()
    console.print(f"[bold cyan]Run[/] [bold]{report.run_id}[/]")
    console.print(f"  Root task: [dim]{report.root_task[:120]}{'…' if len(report.root_task) > 120 else ''}[/]")
    console.print(f"  Strategy: [dim]{report.strategy}[/]  Started: [dim]{report.started_at}[/]  Finished: [dim]{report.finished_at}[/]")
    console.print()

    # 2. Overview panel
    cost_str = CostEstimator.format_cost(report.estimated_cost_usd)
    overview = (
        f"Duration: [bold]{report.total_duration_seconds:.1f}s[/]  "
        f"Tasks: [green]{report.completed_tasks}[/]/[bold]{report.total_tasks}[/] completed, "
        f"[red]{report.failed_tasks}[/] failed  "
        f"Cost: [dim]{cost_str}[/]  "
        f"Models: [dim]{', '.join(report.models_used) or '—'}[/]"
    )
    console.print(Panel(overview, title="Overview", border_style="dim"))
    console.print()

    # 3. Timeline table
    table = Table(title="Timeline")
    table.add_column("Task", style="dim", max_width=50, overflow="fold")
    table.add_column("Role", style="dim", width=10)
    table.add_column("Status", width=12)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Tools", style="dim", max_width=30, overflow="fold")
    bottleneck_id = report.bottleneck_task_id
    for t in report.tasks:
        desc = (t.description or t.task_id)[:48]
        role = (t.role or "—")
        if t.status == TaskStatus.COMPLETED:
            status = "[green]completed[/]"
        elif t.status == TaskStatus.FAILED:
            status = "[red]failed[/]"
        elif t.status == TaskStatus.PENDING:
            status = "[dim]skipped[/]"
        else:
            status = "[yellow]running[/]"
        dur = f"{t.duration_seconds:.1f}s"
        tools = ", ".join(t.tools_used[:5]) if t.tools_used else "—"
        if len(t.tools_used) > 5:
            tools += "…"
        row_style = ""
        if t.task_id == bottleneck_id:
            row_style = "bold"
            status = "[bold]⚡ bottleneck[/]"
        elif t.status == TaskStatus.FAILED:
            row_style = "red"
        elif t.status == TaskStatus.PENDING:
            row_style = "dim"
        table.add_row(desc, role, status, dur, tools, style=row_style)
    console.print(table)
    console.print()

    # 4. Critical path
    if report.critical_path:
        path_parts = [
            tid + (" [bold](bottleneck)[/]" if tid == report.bottleneck_task_id else "")
            for tid in report.critical_path
        ]
        path_str = " → ".join(path_parts)
    else:
        path_str = "(none)"
    console.print("[bold]Critical path:[/] [dim]" + path_str)
    console.print()

    # 5. Tool usage (aggregate)
    tool_table = Table(title="Tool usage")
    tool_table.add_column("Metric", style="dim")
    tool_table.add_column("Value", justify="right")
    tool_table.add_row("Tools called", str(report.tools_called))
    tool_table.add_row("Success rate", f"{report.tool_success_rate:.1f}%")
    console.print(tool_table)
    console.print()

    # 6. Plain-English Analysis (only if already set; CLI streams and prints after)
    if report.plain_english_analysis:
        console.print(
            Panel(
                report.plain_english_analysis,
                title="Plain-English Analysis",
                border_style="dim",
            )
        )
        console.print()

    # 7. Footer (caller may print again after streaming analysis)
    console.print(f"[dim]Cost estimate: {CostEstimator.format_cost(report.estimated_cost_usd)}[/]")
