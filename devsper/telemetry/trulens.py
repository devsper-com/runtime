"""TruLens observability — default for devsper 2.6.0+.

TruLens records every swarm run (input task → output results) and every agent
call (prompt → completion) into a local SQLite database at
``.devsper/trulens.sqlite`` (same directory as memory.db and tool_analytics.db).

The TruLens dashboard can be launched with::

    from devsper.telemetry import get_trulens_session
    get_trulens_session().run_dashboard()

OTEL spans are still emitted alongside TruLens records — they are complementary.
TruLens is the new *default* export layer; OTEL remains available for
infrastructure-level tracing (Grafana, Jaeger, etc.).

Configuration (devsper.toml):

    [telemetry]
    trulens_enabled = true
    trulens_database_url = ""   # empty = sqlite:///.devsper/trulens.sqlite

Install::

    uv pip install "devsper[trulens]"
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# Default SQLite path — mirrors memory.db / tool_analytics.db location.
_DEFAULT_DB_PATH = ".devsper/trulens.sqlite"
_DEFAULT_DB_URL = f"sqlite:///{_DEFAULT_DB_PATH}"

try:
    from trulens.core import TruSession
    from trulens.apps.custom import TruCustomApp, instrument
    import importlib as _il
    _TRULENS_AVAILABLE = _il.util.find_spec("trulens.feedback") is not None
    if not _TRULENS_AVAILABLE:
        log.debug("trulens.feedback not installed; TruLens recording disabled to avoid spam")
except ImportError:
    _TRULENS_AVAILABLE = False
    TruSession = None  # type: ignore[assignment,misc]
    TruCustomApp = None  # type: ignore[assignment,misc]

    def instrument(fn):  # type: ignore[misc]  # noqa: E306
        """No-op fallback when trulens-core is not installed."""
        return fn


_session: Any = None  # TruSession | None


def init_trulens(
    *,
    database_url: str = "",
    app_name: str = "devsper",
    app_version: str = "",
) -> Any:
    """Initialize global TruLens session (idempotent).

    Defaults to ``sqlite:///.devsper/trulens.sqlite`` — the same ``.devsper/``
    directory used by ``memory.db`` and ``tool_analytics.db``.

    Returns the session on success, or None if trulens-core is not installed
    or initialization fails.
    """
    global _session
    if not _TRULENS_AVAILABLE:
        log.debug("trulens-core not installed; TruLens observability skipped")
        return None
    if _session is not None:
        return _session
    url = database_url.strip() if database_url else _DEFAULT_DB_URL
    # Ensure the .devsper/ directory exists for the default SQLite path.
    if url == _DEFAULT_DB_URL:
        os.makedirs(os.path.dirname(_DEFAULT_DB_PATH), exist_ok=True)
    try:
        _session = TruSession(database_url=url)
        log.info(
            "TruLens session initialized (app=%s v%s db=%s)",
            app_name,
            app_version or "?",
            url,
        )
    except Exception as exc:
        log.warning("TruLens init failed: %s", exc)
    return _session


def get_session() -> Any:
    """Return the active TruLens session, or None."""
    return _session


def make_recorder(
    app: Any,
    *,
    app_name: str = "devsper",
    app_version: str = "",
) -> Any:
    """Wrap an instrumented app with TruCustomApp for recording.

    Returns a TruCustomApp recorder, or None if TruLens is unavailable /
    the session has not been initialized.
    """
    if not _TRULENS_AVAILABLE or _session is None or TruCustomApp is None:
        return None
    try:
        kwargs: dict[str, Any] = {"app_name": app_name}
        if app_version:
            kwargs["app_version"] = app_version
        return TruCustomApp(app, **kwargs)
    except Exception as exc:
        log.warning("TruLens make_recorder failed: %s", exc)
        return None
