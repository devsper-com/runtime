"""
Typed errors with actionable hints. No raw tracebacks shown to end users.
"""

from devsper.cli.ui.theme import err_console
from devsper.cli.ui.components import ErrorPanel

DOCS_BASE = "https://docs.devsper.com"
REPO_ISSUES = "https://github.com/devsper-com/runtime/issues/new"


class devsperError(Exception):
    """Base CLI error with message, hint, docs, exit code."""

    def __init__(
        self,
        message: str,
        hint: str | None = None,
        docs_url: str | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.docs_url = docs_url
        self.exit_code = exit_code


class ProviderConnectionError(devsperError):
    def __init__(self, message: str, provider: str = "") -> None:
        super().__init__(
            message,
            hint="Check your API key with: devsper credentials list",
            docs_url=f"{DOCS_BASE}/providers" if provider else None,
        )


class ConfigNotFoundError(devsperError):
    def __init__(self, message: str = "No configuration found.") -> None:
        super().__init__(message, hint="Run devsper init to create a configuration")


class RedisConnectionError(devsperError):
    def __init__(self, message: str = "Cannot connect to Redis.") -> None:
        super().__init__(
            message,
            hint="Start Redis with: docker run -p 6379:6379 redis:7-alpine",
        )


class NoWorkersError(devsperError):
    def __init__(self, message: str = "No workers available.") -> None:
        super().__init__(message, hint="Start a worker with: devsper node start --role worker")


class ModelNotFoundError(devsperError):
    def __init__(self, model_name: str) -> None:
        super().__init__(
            f"Model not found: {model_name}",
            hint="Available models: devsper doctor | grep model",
        )


def print_error(e: devsperError, json_output: bool = False) -> None:
    """Print error to stderr. If json_output, print {\"error\", \"hint\", \"exit_code\"}."""
    if json_output:
        import json
        err_console.print(json.dumps({
            "error": e.message,
            "hint": e.hint,
            "docs_url": getattr(e, "docs_url", None),
            "exit_code": e.exit_code,
        }))
        return
    panel = ErrorPanel(e.message, hint=e.hint, docs_url=getattr(e, "docs_url", None))
    err_console.print(panel)


def print_unexpected_error(exc: BaseException, json_output: bool = False) -> None:
    """Condensed traceback (last 3 frames) + bug report hint."""
    if json_output:
        import json
        err_console.print(json.dumps({
            "error": str(exc),
            "hint": "Unexpected error; see logs.",
            "exit_code": 1,
        }))
        return
    import traceback
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    # Last 3 frames only
    condensed = "".join(tb_lines[-3:]) if len(tb_lines) >= 3 else "".join(tb_lines)
    from devsper.cli.ui.theme import THEME
    from rich.panel import Panel
    from rich.console import Console
    c = Console(stderr=True, theme=THEME)
    c.print(Panel(condensed.strip(), title="Traceback", border_style="hive.dim"))
    c.print("\n[dim]This looks like a bug. Please report it:[/]")
    c.print(f"  [link={REPO_ISSUES}]{REPO_ISSUES}[/]")
    try:
        import devsper
        c.print(f"  devsper {getattr(devsper, '__version__', '?')}  Python {__import__('sys').version.split()[0]}  {__import__('platform').system()}")
    except Exception:
        pass
