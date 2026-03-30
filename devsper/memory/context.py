"""Process/async context for memory store + namespace (tools + agent execution)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_current_store: ContextVar[object | None] = ContextVar("devsper_memory_store", default=None)
_current_namespace: ContextVar[str | None] = ContextVar("devsper_memory_namespace", default=None)
_current_run_id: ContextVar[str | None] = ContextVar("devsper_memory_run_id", default=None)


def attach_memory_context(
    store: object | None,
    namespace: str | None,
    run_id: str | None = None,
) -> tuple[Token[object | None], Token[str | None], Token[str | None]]:
    return (
        _current_store.set(store),
        _current_namespace.set(namespace),
        _current_run_id.set(run_id),
    )


def detach_memory_context(
    tokens: tuple[Token[object | None], Token[str | None], Token[str | None]]
) -> None:
    _current_store.reset(tokens[0])
    _current_namespace.reset(tokens[1])
    _current_run_id.reset(tokens[2])


def get_effective_memory_store():
    """Prefer agent/router store when set; else process default SQLite store."""
    s = _current_store.get()
    if s is not None:
        return s
    from devsper.memory.memory_store import get_default_store

    return get_default_store()


def get_effective_memory_namespace() -> str | None:
    """Active namespace for tool memory ops (None = legacy global/run default)."""
    return _current_namespace.get()


def get_effective_run_id() -> str | None:
    """Active run id for shared memory scope."""
    return _current_run_id.get()
