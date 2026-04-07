"""
GEPA prompt optimizer backend.

Uses an evolutionary/LLM-driven approach to iteratively improve prompts.
If gepa (the library) is installed it uses it directly; otherwise falls back
to a built-in evolutionary loop using devsper's own generate() so you can
use this backend without any extra dependencies.

Requires (optional): pip install devsper[gepa]  (gepa>=0.1)
"""

from __future__ import annotations

import logging
import random

from devsper.prompt_optimizer.base import OptimizeRequest, OptimizeResult, PromptOptimizerBackend

logger = logging.getLogger(__name__)


class GEPABackend(PromptOptimizerBackend):
    """
    GEPA (Generative Evolutionary Prompt Architect) backend.

    When the ``gepa`` package is installed, delegates to it.
    Otherwise runs a built-in LLM-driven evolutionary loop:

    1. Seed population with mutated variants of the base prompt.
    2. Score each variant on the provided examples.
    3. Select survivors, generate next generation, repeat.

    Config keys:
        n_iterations: number of evolutionary generations (default: 10)
        population_size: variants per generation (default: 5)
        model: LLM model for mutation + scoring (uses request.model)
    """

    def __init__(self, population_size: int = 5):
        self._population_size = population_size

    @property
    def name(self) -> str:
        return "gepa"

    async def health(self) -> bool:
        return True  # built-in fallback always available

    async def optimize(self, request: OptimizeRequest) -> OptimizeResult:
        try:
            import gepa  # noqa: F401
            return await self._optimize_via_library(request)
        except ImportError:
            return await self._optimize_builtin(request)

    # ------------------------------------------------------------------
    # Library path (gepa package installed)
    # ------------------------------------------------------------------

    async def _optimize_via_library(self, request: OptimizeRequest) -> OptimizeResult:
        import asyncio
        import os
        import gepa

        def _run() -> str:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            examples = [
                {"input": task, "output": output}
                for task, output in request.examples
            ]

            def metric(prompt: str, output: str, expected: str) -> float:
                if request.metric is not None:
                    from devsper.evals.types import EvalCase
                    fake = EvalCase(id="opt", task="", expected=expected, role=request.role)
                    return request.metric(fake, output)
                return 1.0 if expected.lower() in output.lower() else 0.0

            optimizer = gepa.Gepa(
                model=request.model,
                initial_prompt=request.base_prompt,
                examples=examples,
                metric=metric,
                n_iterations=request.n_iterations,
                population_size=self._population_size,
                api_key=api_key,
            )
            return optimizer.run()

        optimized_prompt = await asyncio.to_thread(_run)
        return OptimizeResult(
            optimized_prompt=optimized_prompt,
            backend=self.name,
            metadata={"gepa": "library"},
        )

    # ------------------------------------------------------------------
    # Built-in evolutionary loop (no gepa package needed)
    # ------------------------------------------------------------------

    async def _optimize_builtin(self, request: OptimizeRequest) -> OptimizeResult:
        import asyncio

        result = await asyncio.to_thread(self._evolve_sync, request)
        return result

    def _evolve_sync(self, request: OptimizeRequest) -> OptimizeResult:
        from devsper.utils.models import generate

        population = self._seed_population(request.base_prompt, request.model, generate)
        best_prompt = request.base_prompt
        best_score = self._score_prompt(request.base_prompt, request.examples, request.metric)
        score_before = best_score

        for generation in range(request.n_iterations):
            scored = []
            for prompt in population:
                score = self._score_prompt(prompt, request.examples, request.metric)
                scored.append((score, prompt))

            scored.sort(key=lambda x: -x[0])
            if scored[0][0] > best_score:
                best_score = scored[0][0]
                best_prompt = scored[0][1]
                logger.debug("[gepa] Gen %d: new best score=%.3f", generation, best_score)

            # Select top survivors
            survivors = [p for _, p in scored[: max(1, self._population_size // 2)]]

            # Generate next generation via LLM mutation
            population = list(survivors)
            while len(population) < self._population_size:
                parent = random.choice(survivors)
                mutant = self._mutate(parent, request.role, request.model, generate)
                population.append(mutant)

        return OptimizeResult(
            optimized_prompt=best_prompt,
            backend=self.name,
            score_before=score_before,
            score_after=best_score,
            metadata={"gepa": "builtin", "generations": request.n_iterations},
        )

    def _seed_population(self, base_prompt: str, model: str, generate) -> list[str]:
        """Generate initial population by mutating the base prompt."""
        variants = [base_prompt]
        mutation_prompt = (
            f"You are improving an AI agent's system prompt. "
            f"Generate a slightly different version of the following prompt "
            f"that preserves the core role but varies the instructions, tone, or emphasis.\n\n"
            f"Original prompt:\n{base_prompt}\n\n"
            f"Output ONLY the new prompt text, nothing else."
        )
        for _ in range(self._population_size - 1):
            try:
                variant = generate(model, mutation_prompt)
                variants.append((variant or base_prompt).strip())
            except Exception:
                variants.append(base_prompt)
        return variants

    def _mutate(self, prompt: str, role: str, model: str, generate) -> str:
        """Generate a mutated version of a prompt."""
        mutation_prompt = (
            f"Improve this {role} agent system prompt. Keep the same role but "
            f"make it clearer, more specific, or better at the task.\n\n"
            f"Prompt:\n{prompt}\n\n"
            f"Output ONLY the improved prompt, nothing else."
        )
        try:
            result = generate(model, mutation_prompt)
            return (result or prompt).strip()
        except Exception:
            return prompt

    def _score_prompt(
        self,
        prompt: str,
        examples: list[tuple[str, str]],
        metric,
    ) -> float:
        """Score a prompt by running examples through generate() with it."""
        from devsper.utils.models import generate

        if not examples:
            return 0.0

        scores = []
        for task, expected in examples[:5]:  # cap at 5 to keep cost low
            full_prompt = f"{prompt}\n\nTask: {task}"
            try:
                actual = generate("gpt-4o-mini", full_prompt) or ""
                if metric is not None:
                    from devsper.evals.types import EvalCase
                    fake = EvalCase(id="s", task=task, expected=expected, role="general")
                    scores.append(float(metric(fake, actual)))
                else:
                    scores.append(1.0 if expected.lower() in actual.lower() else 0.0)
            except Exception:
                scores.append(0.0)

        return sum(scores) / len(scores) if scores else 0.0
