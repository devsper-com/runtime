"""
CLI UI: theme, components, logging, progress, errors.
All CLI code imports from devsper.cli.ui, never from rich directly.
"""

from devsper.cli.ui.theme import THEME, console, err_console, reconfigure_console
from devsper.cli.ui.components import (
    CostDisplay,
    ErrorPanel,
    devsperHeader,
    RoleTag,
    SectionHeader,
    StatusBadge,
    TaskRow,
)
from devsper.cli.ui.errors import (
    ConfigNotFoundError,
    devsperError,
    ModelNotFoundError,
    NoWorkersError,
    ProviderConnectionError,
    RedisConnectionError,
    print_error,
    print_unexpected_error,
)
from devsper.cli.ui.logging import get_logger, set_log_level, get_log_level, devsperLogger
from devsper.cli.ui.progress import devsperProgress, progress_spinner_style
from devsper.cli.ui.run_view import RunViewState, run_live_view, print_run_summary

try:
    from devsper.cli.ui.onboarding import run_init_wizard
except ImportError:
    run_init_wizard = None  # type: ignore[misc, assignment]

__all__ = [
    "CostDisplay",
    "ConfigNotFoundError",
    "ErrorPanel",
    "devsperError",
    "devsperHeader",
    "devsperLogger",
    "devsperProgress",
    "ModelNotFoundError",
    "NoWorkersError",
    "ProviderConnectionError",
    "RedisConnectionError",
    "RoleTag",
    "SectionHeader",
    "StatusBadge",
    "TaskRow",
    "THEME",
    "console",
    "err_console",
    "get_logger",
    "get_log_level",
    "print_error",
    "print_unexpected_error",
    "print_run_summary",
    "progress_spinner_style",
    "reconfigure_console",
    "run_live_view",
    "RunViewState",
    "run_init_wizard",
    "set_log_level",
]
