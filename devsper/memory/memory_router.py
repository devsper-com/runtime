"""
Memory router: determine which memories are relevant to a task and return context for the agent.
"""

from devsper.memory.memory_index import MemoryIndex
from devsper.memory.platform_memory import PlatformMemoryStore
from devsper.memory.memory_store import MemoryStore
from devsper.memory.memory_types import MemoryRecord


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
    ) -> None:
        self.store = store or _build_memory_store()
        self.index = index or MemoryIndex(self.store)
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
        if inject_records:
            lines.append("USER INJECTIONS (high priority):")
            for r in inject_records:
                lines.append(f"- {r.content[:1000]}{'...' if len(r.content) > 1000 else ''}")
        records = self.get_relevant_memory(task)
        if records:
            if lines:
                lines.append("")
            lines.append("RELEVANT MEMORY (previous research notes, findings, artifacts):")
            for r in records:
                lines.append(
                    f"- [{r.memory_type.value}] {r.source_task or 'general'}: "
                    f"{r.content[:500]}{'...' if len(r.content) > 500 else ''}"
                )
        return "\n".join(lines) if lines else ""


def _build_memory_store() -> MemoryStore | PlatformMemoryStore:
    try:
        from devsper.config import get_config

        cfg = get_config()
        backend = getattr(cfg.memory, "backend", "local")
        if backend == "platform":
            return PlatformMemoryStore(
                base_url=getattr(cfg.memory, "platform_api_url", ""),
                org_slug=getattr(cfg.memory, "platform_org_slug", ""),
            )
    except Exception:
        pass
    return MemoryStore()
