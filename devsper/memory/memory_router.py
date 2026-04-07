"""
Memory router: determine which memories are relevant to a task and return context for the agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from devsper.memory.memory_index import MemoryIndex
from devsper.memory.memory_store import MemoryStore
from devsper.memory.memory_types import MemoryRecord

if TYPE_CHECKING:
    from devsper.memory.providers.base import MemoryBackend


class MemoryRouter:
    """
    Routes task descriptions to relevant memories (e.g. research, papers, codebase)
    and formats them as context for the agent. Only memories above min_similarity
    are included to avoid injecting off-topic context.
    """

    def __init__(
        self,
        store: MemoryStore | None = None,
        index: MemoryIndex | None = None,
        top_k: int = 10,
        min_similarity: float = 0.55,
        default_namespace: str | None = None,
        ranking_backend: str | None = None,
        backend: "MemoryBackend | None" = None,
    ) -> None:
        # Resolve the sync store from whichever source is provided
        if backend is not None:
            self.store = _sync_store_from_backend(backend)
        elif store is not None:
            self.store = store
        else:
            self.store = _build_memory_store()

        # Ranking backend only affects retrieval/ranking; persistence remains store-backed.
        try:
            from devsper.config import get_config

            cfg = get_config()
            effective_backend = ranking_backend or getattr(cfg.memory, "backend", "local")
        except Exception:
            effective_backend = ranking_backend or "local"
        self.ranking_backend = effective_backend
        self.index = index or MemoryIndex(self.store, ranking_backend=effective_backend)
        self.top_k = top_k
        self.min_similarity = min_similarity
        self.default_namespace = default_namespace

    def get_relevant_memory(self, task: str) -> list[MemoryRecord]:
        """
        Return memories relevant to the task (semantic search).
        Only returns records with similarity >= min_similarity to avoid off-topic injection.
        """
        return self.index.query_memory(
            task,
            top_k=self.top_k,
            min_similarity=self.min_similarity,
            namespace=self.default_namespace,
        )

    def get_memory_context(self, task: str) -> str:
        """
        Format relevant memories as a string block for injection into the agent prompt.
        User injections (tag user_injection) are always included first. Then semantic results.
        Empty if no memories meet the relevance threshold.
        """
        lines = []
        inject_records = self.store.list_memory(
            tag_contains="user_injection", limit=10, namespace=self.default_namespace
        )
        ranked_records = self.get_relevant_memory(task)

        if self.ranking_backend == "supermemory":
            from devsper.memory.supermemory_rust_ranker import format_memory_context

            # Rust does the prompt assembly (including dedup of user_injections).
            return format_memory_context(
                user_injections=inject_records,
                ranked_candidates=ranked_records,
            )

        # Non-supermemory: preserve legacy prompt formatting.
        if inject_records:
            lines.append("USER INJECTIONS (high priority):")
            for r in inject_records:
                lines.append(
                    f"- {r.content[:1000]}{'...' if len(r.content) > 1000 else ''}"
                )

        # Avoid duplicating user injections in the legacy path.
        ranked_records = [
            r
            for r in ranked_records
            if not any(t == "user_injection" for t in (getattr(r, "tags", None) or []))
        ]

        if ranked_records:
            if lines:
                lines.append("")
            lines.append(
                "RELEVANT MEMORY (previous research notes, findings, artifacts):"
            )
            for r in ranked_records:
                lines.append(
                    f"- [{r.memory_type.value}] {r.source_task or 'general'}: "
                    f"{r.content[:500]}{'...' if len(r.content) > 500 else ''}"
                )

        return "\n".join(lines) if lines else ""


def _sync_store_from_backend(backend: "MemoryBackend"):
    """
    Return a sync-compatible store from a MemoryBackend.
    Backends with get_sync_store() (sqlite, redis, platform) return their underlying store.
    Async-only backends (vektori, snowflake) return an _AsyncBridgeStore shim.
    """
    if hasattr(backend, "get_sync_store"):
        return backend.get_sync_store()
    from devsper.memory.context import _AsyncBridgeStore

    return _AsyncBridgeStore(backend)


def _build_memory_store():
    """Build the default memory store via the provider factory."""
    try:
        from devsper.memory.providers.factory import get_memory_provider

        backend = get_memory_provider()
        return _sync_store_from_backend(backend)
    except Exception:
        pass
    # Hard fallback: bare SQLite
    return MemoryStore()
