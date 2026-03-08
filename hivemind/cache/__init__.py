"""Task result cache: hash task identity and store/retrieve results."""

from hivemind.cache.hashing import task_hash
from hivemind.cache.task_cache import TaskCache

__all__ = ["task_hash", "TaskCache"]
