from __future__ import annotations
import uuid
from typing import Callable
from devsper.compiler.ir import NodeSpec
from .state import AgentState


def build_agent_node(node: NodeSpec) -> Callable[[AgentState], dict]:
    """
    Build a LangGraph node function for a standard agent node.

    Runs Agent.run_task() for real LLM execution when a model is configured.
    Falls back to a stub result when model_hint is "stub" or Agent construction
    fails (e.g. no API keys in test environments).
    """
    node_id = node.id
    node_role = node.role
    model_hint = node.model_hint  # "fast" | "mid" | "slow" | specific model name

    def agent_node(state: AgentState) -> dict:
        task_text = state.get("task", "")
        prior_results = state.get("results", {})

        # Build context from previous nodes so this node can build on prior work
        context = ""
        if prior_results:
            context = "\n\n".join(
                f"[{nid}]: {res}" for nid, res in prior_results.items()
            )
            task_text = f"{task_text}\n\nPrior work:\n{context}" if context else task_text

        result_text = _run_agent(
            task=f"{node_role}. Task: {task_text}",
            model_hint=model_hint,
            node_id=node_id,
            fallback=f"[{node_role}] completed",
        )

        return {
            "results": {**prior_results, node_id: result_text},
            "completed_nodes": state.get("completed_nodes", []) + [node_id],
        }

    return agent_node


def build_mutation_checkpoint_node(node: NodeSpec) -> Callable[[AgentState], dict]:
    """
    Build a LangGraph node function for a mutation checkpoint node.

    Runs the agent task and parses any MutationRequest blocks from the output.
    Validated mutations are appended to state["pending_mutations"] for
    GraphRuntime to apply after this node completes.
    """
    node_id = node.id
    node_role = node.role
    model_hint = node.model_hint

    def mutation_node(state: AgentState) -> dict:
        task_text = state.get("task", "")
        prior_results = state.get("results", {})
        context = "\n\n".join(f"[{nid}]: {res}" for nid, res in prior_results.items())
        full_task = f"{node_role}. Task: {task_text}"
        if context:
            full_task += f"\n\nPrior work:\n{context}"

        result_text = _run_agent(
            task=full_task,
            model_hint=model_hint,
            node_id=node_id,
            fallback=f"[{node_role}] mutation checkpoint reached",
        )

        # Parse MutationRequest JSON blocks from output (if any)
        mutations = _extract_mutations(result_text)
        existing_mutations = state.get("pending_mutations", [])

        return {
            "results": {**prior_results, node_id: result_text},
            "completed_nodes": state.get("completed_nodes", []) + [node_id],
            "pending_mutations": existing_mutations + mutations,
        }

    return mutation_node


def _run_agent(
    task: str,
    model_hint: str,
    node_id: str,
    fallback: str,
) -> str:
    """
    Invoke Agent.run_task() and return the result string.
    Falls back to `fallback` if agent construction fails or model is unavailable.
    """
    try:
        from devsper.agents.agent import Agent
        from devsper.types.task import Task

        # Map model_hint to a concrete model name.
        # Caller can override by passing a full model name (e.g. "gemma4:e4b").
        model = _resolve_model(model_hint)

        agent = Agent(model_name=model, use_tools=False)
        t = Task(id=str(uuid.uuid4()), description=task)
        return agent.run_task(t)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).debug(
            "graph.nodes[%s]: agent run failed (%s), using fallback", node_id, exc
        )
        return fallback


def _resolve_model(model_hint: str) -> str:
    """
    Convert model_hint to a concrete model name.
    - "fast" → "mock" (fast unit tests) unless DEVSPER_FAST_MODEL is set
    - "mid"  → DEVSPER_MID_MODEL or "mock"
    - "slow" → DEVSPER_SLOW_MODEL or "mock"
    - anything else → pass through (e.g. "gemma4:e4b", "gpt-4o")
    """
    import os
    if model_hint == "fast":
        return os.environ.get("DEVSPER_FAST_MODEL", "mock")
    if model_hint == "mid":
        return os.environ.get("DEVSPER_MID_MODEL", "mock")
    if model_hint == "slow":
        return os.environ.get("DEVSPER_SLOW_MODEL", "mock")
    return model_hint or "mock"


def _extract_mutations(text: str) -> list[dict]:
    """
    Parse MutationRequest JSON blocks from agent output.
    Blocks must be wrapped in ```mutation ... ``` fences.
    """
    import json
    import re
    mutations = []
    for block in re.findall(r"```mutation\s*\n(.*?)\n```", text, re.DOTALL):
        try:
            data = json.loads(block.strip())
            if isinstance(data, dict) and "op" in data:
                mutations.append(data)
        except Exception:
            pass
    return mutations
