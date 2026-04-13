from __future__ import annotations
import uuid
from typing import TypedDict, Annotated
import operator


class AgentState(TypedDict):
    """Typed LangGraph state passed between graph nodes."""
    task: str
    run_id: str
    messages: Annotated[list[dict], operator.add]  # append-only via LangGraph
    results: dict[str, str]          # node_id → result text
    pending_mutations: list[dict]    # queued MutationRequests (serialized)
    graph_spec: dict                 # serialized current GraphSpec (for recompile)
    budget_used: float
    completed_nodes: list[str]


def initial_state(task: str, run_id: str = "") -> AgentState:
    """Create a fresh AgentState with sensible defaults."""
    return AgentState(
        task=task,
        run_id=run_id or str(uuid.uuid4()),
        messages=[],
        results={},
        pending_mutations=[],
        graph_spec={},
        budget_used=0.0,
        completed_nodes=[],
    )
