"""
CLI UI: theme, components, logging, progress, errors.
All CLI code imports from hivemind.cli.ui, never from rich directly.
"""

from hivemind.cli.ui.theme import THEME, console, err_console, reconfigure_console
from hivemind.cli.ui.components import (
    CostDisplay,
    ErrorPanel,
    HivemindHeader,
    RoleTag,
    SectionHeader,
    StatusBadge,
    TaskRow,
)
from hivemind.cli.ui.errors import (
    ConfigNotFoundError,
    HivemindError,
    ModelNotFoundError,
    NoWorkersError,
    ProviderConnectionError,
    RedisConnectionError,
    print_error,
    print_unexpected_error,
)
from hivemind.cli.ui.logging import get_logger, set_log_level, get_log_level, HivemindLogger
from hivemind.cli.ui.progress import HivemindProgress, progress_spinner_style
from hivemind.cli.ui.run_view import RunViewState, run_live_view, print_run_summary

try:
    from hivemind.cli.ui.onboarding import run_init_wizard
except ImportError:
    run_init_wizard = None  # type: ignore[misc, assignment]

__all__ = [
    "CostDisplay",
    "ConfigNotFoundError",
    "ErrorPanel",
    "HivemindError",
    "HivemindHeader",
    "HivemindLogger",
    "HivemindProgress",
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
