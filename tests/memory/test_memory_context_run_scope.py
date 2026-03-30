from devsper.memory.context import (
    attach_memory_context,
    detach_memory_context,
    get_effective_memory_namespace,
    get_effective_run_id,
)


def test_memory_context_tracks_run_scope():
    tokens = attach_memory_context(store=None, namespace="project:abc", run_id="run-123")
    try:
        assert get_effective_memory_namespace() == "project:abc"
        assert get_effective_run_id() == "run-123"
    finally:
        detach_memory_context(tokens)

