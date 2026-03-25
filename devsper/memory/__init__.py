"""
Swarm memory: persistent store, semantic index, and router for agent recall.

- memory_types: EpisodicMemory, SemanticMemory, ArtifactMemory, ResearchMemory
- memory_store: SQLite-backed store (store, retrieve, delete, list)
- memory_index: vector/semantic search (query_memory, top_k)
- memory_router: select relevant memories for a task
"""

from devsper.memory.memory_types import (
    EpisodicMemory,
    SemanticMemory,
    ArtifactMemory,
    ResearchMemory,
    MemoryRecord,
    MemoryType,
)
from devsper.memory.memory_store import MemoryStore
from devsper.memory.memory_index import MemoryIndex
try:
    from devsper.memory.memory_router import MemoryRouter
except Exception:
    # Some backends may require optional HTTP dependencies (e.g. `requests`).
    # Keep local store/index usable even when optional dependencies are absent.
    MemoryRouter = None  # type: ignore[assignment]

__all__ = [
    "EpisodicMemory",
    "SemanticMemory",
    "ArtifactMemory",
    "ResearchMemory",
    "MemoryRecord",
    "MemoryType",
    "MemoryStore",
    "MemoryIndex",
]

if MemoryRouter is not None:
    __all__.append("MemoryRouter")

# Optional: import submodules for summarizer, namespaces, scoring
# from devsper.memory import summarizer, namespaces, scoring
