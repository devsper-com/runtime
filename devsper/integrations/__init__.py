"""Optional bridges between Devsper and popular agent frameworks (LangChain, LangGraph)."""

from __future__ import annotations

__all__ = [
    "langchain_task",
    "run_langchain_runnable",
    "stringify_langchain_output",
    "LANGCHAIN_TASK_PREFIX",
    "compiled_graph_to_tasks",
    "default_list_merge_state",
    "run_compiled_graph_as_devsper_tasks",
]


def __getattr__(name: str):
    if name in (
        "langchain_task",
        "run_langchain_runnable",
        "stringify_langchain_output",
        "LANGCHAIN_TASK_PREFIX",
    ):
        from devsper.integrations import langchain_adapter as m

        return getattr(m, name)
    if name in (
        "compiled_graph_to_tasks",
        "default_list_merge_state",
        "run_compiled_graph_as_devsper_tasks",
    ):
        from devsper.integrations import langgraph_adapter as m

        return getattr(m, name)
    raise AttributeError(name)
