from __future__ import annotations
from typing import Callable, Any
from .ir import GraphSpec, NodeSpec


def compile_graph(spec: GraphSpec) -> Any:
    """
    Compile a GraphSpec into a compiled LangGraph StateGraph.
    Requires devsper.graph.state and devsper.graph.nodes (Plan 2).
    Falls back to stub node functions if Plan 2 is not yet implemented.
    """
    from langgraph.graph import StateGraph, END

    try:
        from devsper.graph.state import AgentState
        from devsper.graph.nodes import build_agent_node, build_mutation_checkpoint_node
    except ImportError:
        # Plan 2 not yet implemented — use identity stubs for testing compiler in isolation
        AgentState = dict  # type: ignore[assignment,misc]
        build_agent_node = _build_agent_node_fn  # type: ignore[assignment]
        build_mutation_checkpoint_node = _build_mutation_node_fn  # type: ignore[assignment]

    builder = StateGraph(AgentState)
    node_ids = {n.id for n in spec.nodes}

    for node in spec.nodes:
        if node.is_mutation_point:
            fn = build_mutation_checkpoint_node(node)
        else:
            fn = build_agent_node(node)
        builder.add_node(node.id, fn)

    for edge in spec.edges:
        dst = edge.dst if edge.dst in node_ids else END
        if edge.condition:
            next_node = _next_unconditional(spec, edge.src) or END
            builder.add_conditional_edges(
                edge.src,
                _make_condition_router(edge.condition, edge.dst, next_node),
            )
        else:
            builder.add_edge(edge.src, dst)

    # Wire last node(s) with no outgoing edges to END
    src_ids = {e.src for e in spec.edges}
    for node in spec.nodes:
        if node.id not in src_ids:
            builder.add_edge(node.id, END)

    builder.set_entry_point(_find_entry(spec))
    return builder.compile()


def _find_entry(spec: GraphSpec) -> str:
    """Node with no incoming edges is the entry point."""
    dst_ids = {e.dst for e in spec.edges}
    candidates = [n.id for n in spec.nodes if n.id not in dst_ids]
    return candidates[0] if candidates else spec.nodes[0].id


def _next_unconditional(spec: GraphSpec, src_id: str) -> str | None:
    for edge in spec.edges:
        if edge.src == src_id and edge.condition is None:
            return edge.dst
    return None


def _make_condition_router(condition_expr: str, true_dst: str, false_dst: str) -> Callable:
    def route(state: dict) -> str:
        try:
            return true_dst if eval(condition_expr, {"state": state}) else false_dst  # noqa: S307
        except Exception:
            return false_dst
    return route


# Stub node builders used when devsper.graph is not yet implemented
def _build_agent_node_fn(node: NodeSpec) -> Callable:
    def agent_node(state: dict) -> dict:
        return state
    return agent_node


def _build_mutation_node_fn(node: NodeSpec) -> Callable:
    def mutation_node(state: dict) -> dict:
        return state
    return mutation_node
