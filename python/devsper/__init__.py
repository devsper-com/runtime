from devsper._core import (
    NodeSpec,
    WorkflowIr,
    load_workflow,
    run,
    run_async,
    run_specs,
    run_specs_async,
    run_workflow,
    run_workflow_async,
)


def __getattr__(name):
    """Lazy import for optional dependencies."""
    if name == "VektoriMemoryBridge":
        from devsper._vektori_bridge import VektoriMemoryBridge

        return VektoriMemoryBridge
    raise AttributeError(f"module 'devsper' has no attribute {name!r}")


__all__ = [
    "NodeSpec",
    "VektoriMemoryBridge",
    "WorkflowIr",
    "load_workflow",
    "run",
    "run_async",
    "run_specs",
    "run_specs_async",
    "run_workflow",
    "run_workflow_async",
]
