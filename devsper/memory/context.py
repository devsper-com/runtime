"""Process/async context for memory store + namespace (tools + agent execution)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_current_store: ContextVar[object | None] = ContextVar("devsper_memory_store", default=None)
_current_namespace: ContextVar[str | None] = ContextVar("devsper_memory_namespace", default=None)


def attach_memory_context(store: object | None, namespace: str | None) -> tuple[Token[object | None], Token[str | None]]:
    return (_current_store.set(store), _current_namespace.set(namespace))


def detach_memory_context(tokens: tuple[Token[object | None], Token[str | None]]) -> None:
    _current_store.reset(tokens[0])
    _current_namespace.reset(tokens[1])


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
