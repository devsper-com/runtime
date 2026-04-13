from __future__ import annotations
import logging
from typing import Any
from devsper.compiler.ir import GraphSpec
from devsper.compiler.codegen import compile_graph
from .state import AgentState, initial_state
from .mutations import MutationRequest, MutationValidator

logger = logging.getLogger(__name__)


class GraphRuntime:
    """
    Public API over LangGraph StateGraph execution.
    Replaces Swarm as the top-level orchestration entry point.

    Execution flow:
      1. compile GraphSpec → LangGraph StateGraph
      2. invoke graph → final AgentState
      3. if any pending_mutations in state, validate + apply + recompile + resume
    """

    def __init__(self, mutation_validator: MutationValidator | None = None) -> None:
        self._validator = mutation_validator or MutationValidator()

    def compile(self, spec: GraphSpec) -> Any:
        """Compile a GraphSpec to a LangGraph compiled graph."""
        return compile_graph(spec)

    def run_spec(
        self,
        spec: GraphSpec,
        task: str = "",
        state: AgentState | None = None,
        max_mutation_rounds: int = 3,
    ) -> AgentState:
        """
        Synchronously execute a compiled GraphSpec with live Agent calls.
        Handles pending_mutations emitted by MutationCheckpointNodes:
          - validates each mutation
          - applies valid ones to the spec
          - recompiles and re-runs remaining nodes (up to max_mutation_rounds)

        Returns the final AgentState.
        """
        if state is None:
            state = initial_state(task=task)
        elif task:
            state = {**state, "task": task}

        current_spec = spec
        rounds = 0

        while rounds <= max_mutation_rounds:
            compiled = self.compile(current_spec)
            state = compiled.invoke(state)

            pending = state.get("pending_mutations", [])
            if not pending:
                break

            applied_any = False
            for mut_dict in pending:
                try:
                    req = MutationRequest.from_dict(mut_dict)
                except Exception:
                    continue
                if self._validator.validate(req, current_spec):
                    current_spec = self._validator.apply(req, current_spec)
                    logger.info(
                        "GraphRuntime: applied mutation %s (round %d)", req.op, rounds + 1
                    )
                    applied_any = True

            # Clear mutations from state so we don't re-process them
            state = {**state, "pending_mutations": []}

            if not applied_any:
                break
            rounds += 1

        return state

    def run_from_text(
        self,
        text: str,
        optimize_for: str = "balanced",
        population_size: int = 10,
        max_generations: int = 5,
    ) -> AgentState:
        """
        Full pipeline: parse text → GePA optimize → compile → run.
        Convenience method for one-shot execution from prose/TOML/markdown.
        """
        from devsper.compiler.parser import parse
        from devsper.compiler.gepa import optimize, GEPAConfig

        _, seed_spec = parse(text)
        config = GEPAConfig(
            population_size=population_size,
            max_generations=max_generations,
            optimize_for=optimize_for,
        )
        front = optimize(seed_spec, text, config)
        best = front[0]
        return self.run_spec(best, task=text)
