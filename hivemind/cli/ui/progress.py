"""
Styled progress bars for long operations. Amber fill, dim track, consistent columns.
"""

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from hivemind.cli.ui.theme import console

# Spinner names: dots2, line, arrow (Rich built-in)
SPINNER_THINKING = "dots2"
SPINNER_NETWORK = "line"
SPINNER_BUILDING = "arrow"
SPINNER_SUCCESS = "dots2"  # we override with static ✓ when done


def HivemindProgress(
    transient: bool = False,
    console_use: object = None,
) -> Progress:
    """Progress with hive styling: amber bar, dim track, spinner, task count, elapsed."""
    c = console_use or console
    return Progress(
        SpinnerColumn(style="hive.primary", finished_style="hive.success"),
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=30, complete_style="hive.primary", finished_style="hive.success", pulse_style="hive.dim"),
        TaskProgressColumn(style="hive.muted"),
        TimeElapsedColumn(style="hive.muted"),
        console=c,
        transient=transient,
    )


def progress_spinner_style(operation: str) -> str:
    """Spinner style by operation: thinking, network, building, success."""
    return "hive.primary"
