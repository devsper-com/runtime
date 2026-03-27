from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentIdentity:
    name: str
    persona: str
    model: str
    memory_namespace: str
    tools: list[str]
    max_memory_entries: int = 200
    temperature: float = 0.2

    def build_system_prompt(self, base_prompt: str) -> str:
        return f"{self.persona.strip()}\n\n{(base_prompt or '').strip()}".strip()

    def load_memory(self, memory_store, query: str, top_k: int = 5) -> list:
        if memory_store is None:
            return []
        return memory_store.list_memory(limit=min(top_k, self.max_memory_entries), namespace=self.memory_namespace)

    def save_memory(self, memory_store, content: str, metadata: dict) -> None:
        if memory_store is None:
            return
        from devsper.memory.memory_store import generate_memory_id
        from devsper.memory.memory_types import MemoryRecord, MemoryType

        rec = MemoryRecord(
            id=generate_memory_id(),
            memory_type=MemoryType.EPISODIC,
            source_task=str(metadata.get("task_id", "")),
            content=content[:10000],
            tags=["agent_identity", self.name],
            run_id=str(metadata.get("run_id", "")),
        )
        memory_store.store(rec, namespace=self.memory_namespace)
