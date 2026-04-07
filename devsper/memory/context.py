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


def get_effective_memory_backend():
    """
    Return the active MemoryBackend for the current context.
    Prefers the context-var store (set by attach_memory_context) if it is a MemoryBackend,
    otherwise returns the process-level singleton from the factory.
    """
    s = _current_store.get()
    if s is not None and hasattr(s, "health"):
        return s  # it is already a MemoryBackend
    from devsper.memory.providers.factory import get_memory_provider

    return get_memory_provider()


def get_effective_memory_store():
    """
    Legacy: return a synchronous MemoryStore compatible object.
    Backends that wrap a sync store (sqlite, redis, platform) expose get_sync_store().
    Async-only backends (vektori, snowflake) return an _AsyncBridgeStore shim.
    """
    s = _current_store.get()
    if s is not None and not hasattr(s, "health"):
        # Legacy MemoryStore object set directly via attach_memory_context
        return s
    backend = get_effective_memory_backend()
    if hasattr(backend, "get_sync_store"):
        return backend.get_sync_store()
    # Async-only backend: return a sync bridge so legacy callers still work
    return _AsyncBridgeStore(backend)


class _AsyncBridgeStore:
    """
    Sync shim for async-only backends (VektoriBackend, SnowflakeBackend).
    Runs coroutines via asyncio in a thread so sync callers don't need to be async.
    This mirrors the _run_async() pattern already used in server/memory_utils.py.
    """

    def __init__(self, backend) -> None:
        self._backend = backend

    def _run(self, coro):
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)

    def store(self, record, namespace=None):
        return self._run(self._backend.store(record, namespace))

    def retrieve(self, memory_id, namespace=None):
        try:
            return self._run(self._backend.retrieve(memory_id, namespace))
        except NotImplementedError:
            return None

    def delete(self, memory_id, namespace=None):
        try:
            return self._run(self._backend.delete(memory_id, namespace))
        except NotImplementedError:
            return False

    def list_memory(
        self,
        memory_type=None,
        limit=100,
        offset=0,
        tag_contains=None,
        include_archived=False,
        run_id_filter=None,
        namespace=None,
    ):
        return self._run(
            self._backend.list_memory(
                memory_type, limit, offset, tag_contains,
                include_archived, run_id_filter, namespace,
            )
        )

    def list_all_ids(self, memory_type=None, namespace=None):
        return self._run(self._backend.list_all_ids(memory_type, namespace))


def get_effective_memory_namespace() -> str | None:
    """Active namespace for tool memory ops (None = legacy global/run default)."""
    return _current_namespace.get()


def get_effective_run_id() -> str | None:
    """Active run id for shared memory scope."""
    return _current_run_id.get()
