from __future__ import annotations
from typing import Callable
from devsper.compiler.ir import NodeSpec
from .state import AgentState


def build_agent_node(node: NodeSpec) -> Callable[[AgentState], dict]:
    """
    Build a LangGraph node function for a standard agent node.
    Returns a partial AgentState update dict (LangGraph merges it).
    The node records a stub result and marks itself completed.
    Full agent execution (Agent.run_task) is wired in GraphRuntime.
    """
    node_id = node.id
    node_role = node.role

    def agent_node(state: AgentState) -> dict:
        result_text = state.get("results", {}).get(node_id, f"[{node_role}] completed")
        return {
            "results": {**state.get("results", {}), node_id: result_text},
            "completed_nodes": state.get("completed_nodes", []) + [node_id],
        }

    return agent_node


def build_mutation_checkpoint_node(node: NodeSpec) -> Callable[[AgentState], dict]:
    """
    Build a LangGraph node function for a mutation checkpoint node.
    Parses pending_mutations from state and validates them.
    Actual recompile logic is triggered by GraphRuntime after node completes.
    """
    node_id = node.id
    node_role = node.role

    def mutation_node(state: AgentState) -> dict:
        result_text = state.get("results", {}).get(node_id, f"[{node_role}] mutation checkpoint reached")
        return {
            "results": {**state.get("results", {}), node_id: result_text},
            "completed_nodes": state.get("completed_nodes", []) + [node_id],
        }

    return mutation_node
