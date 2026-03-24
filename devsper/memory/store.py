"""
Platform-facing memory storage API (namespaced MemoryStore).

Implementation lives in ``memory_store``; this module is the stable import path
for project/org/run-scoped isolation.
"""

from devsper.memory.memory_store import MemoryStore, generate_memory_id, get_default_store

__all__ = ["MemoryStore", "generate_memory_id", "get_default_store"]
