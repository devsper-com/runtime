"""
Memory namespaces: filter and tag memories by namespace (e.g. research_memory, coding_memory).
Implemented via tags with prefix "ns:" for backward compatibility.
"""

from hivemind.memory.memory_types import MemoryRecord

NAMESPACE_TAG_PREFIX = "ns:"

# Standard namespaces
RESEARCH_MEMORY = "research_memory"
CODING_MEMORY = "coding_memory"
DATASET_MEMORY = "dataset_memory"

DEFAULT_NAMESPACES = [RESEARCH_MEMORY, CODING_MEMORY, DATASET_MEMORY]


def namespace_tag(namespace: str) -> str:
    """Return the tag string for a namespace."""
    return f"{NAMESPACE_TAG_PREFIX}{namespace}"


def add_namespace(record: MemoryRecord, namespace: str) -> MemoryRecord:
    """Add namespace tag to a record (returns new record with tag)."""
    tag = namespace_tag(namespace)
    tags = list(record.tags) if record.tags else []
    if tag not in tags:
        tags.append(tag)
    return record.model_copy(update={"tags": tags})


def record_namespace(record: MemoryRecord) -> str | None:
    """Extract namespace from record tags, or None if none."""
    if not record.tags:
        return None
    for t in record.tags:
        if t.startswith(NAMESPACE_TAG_PREFIX):
            return t[len(NAMESPACE_TAG_PREFIX) :]
    return None


def filter_by_namespace(records: list[MemoryRecord], namespace: str) -> list[MemoryRecord]:
    """Return records that have the given namespace tag."""
    tag = namespace_tag(namespace)
    return [r for r in records if r.tags and tag in r.tags]
