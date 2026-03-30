from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryScope:
    run_id: str
    namespace: str | None


class SharedRunMemory:
    """
    Run-scoped memory facade for safe shared access across agents/tools.
    """

    def __init__(self, store: Any, scope: MemoryScope) -> None:
        self._store = store
        self._scope = scope
        self._lock = threading.RLock()

    @property
    def scope(self) -> MemoryScope:
        return self._scope

    def store(self, record: Any) -> str:
        with self._lock:
            return self._store.store(record, namespace=self._scope.namespace)

    def retrieve(self, memory_id: str) -> Any | None:
        with self._lock:
            return self._store.retrieve(memory_id, namespace=self._scope.namespace)

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            return bool(self._store.delete(memory_id, namespace=self._scope.namespace))

    def list_memory(self, **kwargs: Any) -> list[Any]:
        with self._lock:
            return list(
                self._store.list_memory(namespace=self._scope.namespace, **kwargs)
            )

