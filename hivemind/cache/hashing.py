"""Hash task identity for cache keys: description, dependencies, and optional tool usage."""

import hashlib
import json


def task_hash(
    task_id: str,
    description: str,
    dependencies: list[str],
    tool_usage: str | None = None,
) -> str:
    """
    Produce a stable hash for a task. Used for cache lookup.
    Includes: task id, description, dependencies, and optional tool_usage signature.
    """
    payload = {
        "id": task_id,
        "description": (description or "").strip(),
        "dependencies": sorted(dependencies) if dependencies else [],
        "tool_usage": tool_usage or "",
    }
    blob = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
