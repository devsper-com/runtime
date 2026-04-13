from __future__ import annotations
from typing import Any
from devsper.compiler.ir import GraphSpec
from devsper.compiler.codegen import compile_graph
from .state import AgentState, initial_state


class GraphRuntime:
    """
    Thin public API over LangGraph StateGraph execution.
    Replaces Swarm as the top-level orchestration entry point.
    Full agent execution (Agent.run_task injection) added in later plans.
    """

    def compile(self, spec: GraphSpec) -> Any:
        """Compile a GraphSpec to a LangGraph compiled graph."""
        return compile_graph(spec)

    def run_spec(
        self,
        spec: GraphSpec,
        task: str = "",
        state: AgentState | None = None,
    ) -> AgentState:
        """
        Synchronously execute a compiled GraphSpec.
        Returns the final AgentState.
        """
        compiled = self.compile(spec)
        if state is None:
            state = initial_state(task=task)
        elif task:
            state = {**state, "task": task}
        result = compiled.invoke(state)
        return result
