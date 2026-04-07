"""
DSPy prompt optimizer backend.

Uses DSPy's BootstrapFewShot (fast) or MIPROv2 (thorough) to optimize the
agent system prompt via few-shot example compilation.

Requires: pip install devsper[dspy]  (dspy-ai>=2.4)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from devsper.prompt_optimizer.base import OptimizeRequest, OptimizeResult, PromptOptimizerBackend

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DSPY_OPTIMIZER_MAP = {
    "bootstrap": "BootstrapFewShot",
    "mipro": "MIPROv2",
    "bootstrap_random": "BootstrapFewShotWithRandomSearch",
}


class DSPyBackend(PromptOptimizerBackend):
    """
    DSPy-powered prompt optimizer.

    Config keys (all optional):
        optimizer: "bootstrap" | "mipro" | "bootstrap_random"  (default: "bootstrap")
        max_bootstrapped_demos: int  (default: 4)
        num_candidates: int  (MIPROv2 only, default: 10)
    """

    def __init__(
        self,
        optimizer: str = "bootstrap",
        max_bootstrapped_demos: int = 4,
        num_candidates: int = 10,
        api_key: str | None = None,
    ):
        self._optimizer_name = optimizer
        self._max_bootstrapped_demos = max_bootstrapped_demos
        self._num_candidates = num_candidates
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "dspy"

    async def health(self) -> bool:
        try:
            import dspy  # noqa: F401
            return True
        except ImportError:
            return False

    async def optimize(self, request: OptimizeRequest) -> OptimizeResult:
        try:
            import dspy
        except ImportError as e:
            raise ImportError(
                "DSPy is not installed. Run: pip install 'devsper[dspy]'"
            ) from e

        import asyncio

        result = await asyncio.to_thread(self._optimize_sync, request, dspy)
        return result

    def _optimize_sync(self, request: OptimizeRequest, dspy) -> OptimizeResult:
        import os

        # Configure DSPy LM
        api_key = self._api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        lm = dspy.LM(request.model, api_key=api_key)
        dspy.configure(lm=lm)

        # Define a Signature that matches the agent's prompt structure
        role_desc = request.base_prompt

        class AgentTask(dspy.Signature):
            __doc__ = role_desc

            task: str = dspy.InputField(desc="The task to complete")
            result: str = dspy.OutputField(desc="The completed task output")

        # Build trainset from examples
        trainset = [
            dspy.Example(task=task, result=output).with_inputs("task")
            for task, output in request.examples[: request.max_demos * 4]
        ]

        if not trainset:
            logger.warning("[dspy] No training examples — returning base prompt.")
            return OptimizeResult(
                optimized_prompt=request.base_prompt,
                backend=self.name,
            )

        # Metric: delegate to the eval metric if provided, else non-empty
        def dspy_metric(example, pred, trace=None) -> bool:
            actual = getattr(pred, "result", "") or ""
            if request.metric is not None:
                from devsper.evals.types import EvalCase
                fake_case = EvalCase(
                    id="opt",
                    task=example.task,
                    expected=example.result,
                    role=request.role,
                )
                return request.metric(fake_case, actual) >= 0.5
            return bool(actual.strip())

        # Select and run optimizer
        predictor = dspy.Predict(AgentTask)

        opt_name = _DSPY_OPTIMIZER_MAP.get(self._optimizer_name, "BootstrapFewShot")

        try:
            if opt_name == "MIPROv2":
                from dspy.teleprompt import MIPROv2
                optimizer = MIPROv2(metric=dspy_metric, num_candidates=self._num_candidates)
                optimized = optimizer.compile(predictor, trainset=trainset)
            elif opt_name == "BootstrapFewShotWithRandomSearch":
                from dspy.teleprompt import BootstrapFewShotWithRandomSearch
                optimizer = BootstrapFewShotWithRandomSearch(
                    metric=dspy_metric,
                    max_bootstrapped_demos=self._max_bootstrapped_demos,
                )
                optimized = optimizer.compile(predictor, trainset=trainset)
            else:
                from dspy.teleprompt import BootstrapFewShot
                optimizer = BootstrapFewShot(
                    metric=dspy_metric,
                    max_bootstrapped_demos=self._max_bootstrapped_demos,
                )
                optimized = optimizer.compile(predictor, trainset=trainset)
        except Exception as e:
            logger.warning("[dspy] Compilation failed: %s — returning base prompt.", e)
            return OptimizeResult(
                optimized_prompt=request.base_prompt,
                backend=self.name,
                metadata={"error": str(e)},
            )

        # Extract the compiled instruction (new system prompt)
        optimized_instruction = _extract_instruction(optimized, AgentTask, role_desc)

        # Estimate score delta on trainset
        score_before = _quick_score(predictor, trainset, dspy_metric)
        score_after = _quick_score(optimized, trainset, dspy_metric)

        return OptimizeResult(
            optimized_prompt=optimized_instruction,
            backend=self.name,
            score_before=score_before,
            score_after=score_after,
            metadata={"dspy_optimizer": self._optimizer_name},
        )


def _extract_instruction(program, sig_cls, fallback: str) -> str:
    """Pull the compiled instruction string from a DSPy program."""
    try:
        # DSPy stores the compiled instruction in the predict module
        predict = getattr(program, "predict", program)
        signature = getattr(predict, "signature", None)
        if signature is not None:
            instructions = getattr(signature, "instructions", None)
            if instructions:
                return str(instructions)
        # Fallback: dump extended demos into the prompt
        demos = getattr(predict, "demos", []) or []
        if demos:
            demo_text = "\n".join(
                f"Example:\nTask: {d.get('task', '')}\nResult: {d.get('result', '')}"
                for d in demos[:4]
                if isinstance(d, dict)
            )
            return f"{fallback}\n\n{demo_text}"
    except Exception:
        pass
    return fallback


def _quick_score(program, trainset: list, metric) -> float:
    """Estimate metric on a small trainset sample."""
    try:
        hits = 0
        sample = trainset[:min(5, len(trainset))]
        for ex in sample:
            try:
                pred = program(task=ex.task)
                if metric(ex, pred):
                    hits += 1
            except Exception:
                pass
        return hits / len(sample) if sample else 0.0
    except Exception:
        return 0.0
