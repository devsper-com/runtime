"""
EvalRunner: runs an eval dataset against an agent/swarm and collects scored results.
Optionally triggers prompt optimization on the collected examples.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from devsper.evals.types import EvalCase, EvalResult, EvalSummary, MetricFn

logger = logging.getLogger(__name__)


class EvalRunner:
    """
    Runs EvalCases through a single Agent and scores results.

    Args:
        agent: An instantiated ``Agent`` (devsper.agents.agent.Agent).
        metric: Callable ``(case, actual) -> float``. Use ``get_metric()`` to resolve by name.
        pass_threshold: Score >= this is considered a pass (default 0.5).
        concurrency: Number of cases to run in parallel (default 4).
        optimize_after: If set, run prompt optimization after eval and return
            the optimized prompt. Requires a ``PromptOptimizerBackend``.
        optimizer: Optional ``PromptOptimizerBackend`` instance.
    """

    def __init__(
        self,
        agent: Any,
        metric: MetricFn,
        pass_threshold: float = 0.5,
        concurrency: int = 4,
        optimize_after: bool = False,
        optimizer: Any | None = None,
    ):
        self.agent = agent
        self.metric = metric
        self.pass_threshold = pass_threshold
        self.concurrency = concurrency
        self.optimize_after = optimize_after
        self.optimizer = optimizer

    def run(self, dataset, role: str | None = None) -> EvalSummary:
        """
        Synchronous wrapper around ``run_async``.

        Args:
            dataset: ``EvalDataset`` or list of ``EvalCase``.
            role: Override role filter; if None, uses each case's role.
        """
        return asyncio.run(self.run_async(dataset, role=role))

    async def run_async(self, dataset, role: str | None = None) -> EvalSummary:
        """Run all cases asynchronously with bounded concurrency."""
        from devsper.evals.dataset import EvalDataset

        cases: list[EvalCase] = list(dataset)
        if role:
            cases = [c for c in cases if c.role == role]

        effective_role = role or (cases[0].role if cases else "general")
        semaphore = asyncio.Semaphore(self.concurrency)
        results: list[EvalResult] = []

        async def run_one(case: EvalCase) -> EvalResult:
            async with semaphore:
                return await self._run_case(case)

        tasks = [asyncio.create_task(run_one(c)) for c in cases]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            passed_str = "PASS" if result.passed else "FAIL"
            logger.info(
                "[eval] %s case=%s score=%.2f %s",
                passed_str,
                result.case.id,
                result.score,
                f"error={result.error}" if result.error else "",
            )

        optimizer_backend = "noop"
        if self.optimize_after and self.optimizer is not None:
            optimizer_backend = self.optimizer.name
            summary_so_far = EvalSummary(
                results=results,
                metric_name=getattr(self.metric, "__name__", "custom"),
                role=effective_role,
                pass_threshold=self.pass_threshold,
                optimizer_backend=optimizer_backend,
            )
            await self._run_optimization(summary_so_far, effective_role)

        return EvalSummary(
            results=results,
            metric_name=getattr(self.metric, "__name__", "custom"),
            role=effective_role,
            pass_threshold=self.pass_threshold,
            optimizer_backend=optimizer_backend,
        )

    async def _run_case(self, case: EvalCase) -> EvalResult:
        t0 = time.perf_counter()
        try:
            from devsper.types.task import Task

            task = Task(
                id=case.id,
                description=case.task,
                dependencies=[],
                role=case.role,
            )
            response = await asyncio.to_thread(self.agent.run, task)
            actual = getattr(response, "result", "") or ""
            score = float(self.metric(case, actual))
            return EvalResult(
                case=case,
                actual=actual,
                score=score,
                passed=score >= self.pass_threshold,
                duration_seconds=time.perf_counter() - t0,
            )
        except Exception as e:
            logger.warning("[eval] case=%s failed: %s", case.id, e)
            return EvalResult(
                case=case,
                actual="",
                score=0.0,
                passed=False,
                duration_seconds=time.perf_counter() - t0,
                error=str(e),
            )

    async def _run_optimization(self, summary: EvalSummary, role: str) -> None:
        """Fire optimizer with passing examples as training data."""
        from devsper.agents.roles import get_role_config
        from devsper.prompt_optimizer.base import OptimizeRequest

        examples = summary.as_examples()
        if not examples:
            logger.warning("[eval] No passing examples to optimize from — skipping optimization.")
            return

        role_cfg = get_role_config(role)
        req = OptimizeRequest(
            base_prompt=role_cfg.prompt_prefix,
            examples=examples,
            metric=self.metric,
            role=role,
            model=getattr(self.agent, "model_name", "gpt-4o-mini"),
        )
        try:
            opt_result = await self.optimizer.optimize(req)
            logger.info(
                "[eval] Optimization complete via %s: score_before=%.2f score_after=%.2f",
                opt_result.backend,
                opt_result.score_before or 0.0,
                opt_result.score_after or 0.0,
            )
            _save_optimized_prompt(role, opt_result.optimized_prompt)
        except Exception as e:
            logger.warning("[eval] Optimization failed: %s", e)


def _save_optimized_prompt(role: str, prompt: str) -> None:
    """Persist an optimized prompt to .devsper/optimized_prompts/{role}.txt"""
    import json
    from pathlib import Path

    out_dir = Path(".devsper/optimized_prompts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{role}.json"
    out_file.write_text(json.dumps({"role": role, "prompt_prefix": prompt}, indent=2))
    logger.info("[eval] Optimized prompt saved to %s", out_file)
