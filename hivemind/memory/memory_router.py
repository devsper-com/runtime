"""
Memory router: determine which memories are relevant to a task and return context for the agent.
"""

from hivemind.memory.memory_index import MemoryIndex
from hivemind.memory.memory_store import MemoryStore
from hivemind.memory.memory_types import MemoryRecord, MemoryType


class MemoryRouter:
    """
    Routes task descriptions to relevant memories (e.g. research, papers, codebase)
    and formats them as context for the agent.
    """

    def __init__(
        self,
        store: MemoryStore | None = None,
        index: MemoryIndex | None = None,
        top_k: int = 10,
    ) -> None:
        self.store = store or MemoryStore()
        self.index = index or MemoryIndex(self.store)
        self.top_k = top_k

    def get_relevant_memory(self, task: str) -> list[MemoryRecord]:
        """
        Return memories relevant to the task (semantic search).
        Example: task = "analyze diffusion model papers" -> research memory, paper summaries.
        """
        return self.index.query_memory(task, top_k=self.top_k)

    def get_memory_context(self, task: str) -> str:
        """
        Format relevant memories as a string block for injection into the agent prompt.
        """
        records = self.get_relevant_memory(task)
        if not records:
            return ""
        lines = ["RELEVANT MEMORY (previous research notes, findings, artifacts):"]
        for r in records:
            lines.append(f"- [{r.memory_type.value}] {r.source_task or 'general'}: {r.content[:500]}{'...' if len(r.content) > 500 else ''}")
        return "\n".join(lines)
