"""HTTP client for remote polyglot agents."""

from __future__ import annotations

import itertools
import time

import httpx

from devsper.protocol.schema import AgentExecuteRequest
from devsper.telemetry.pricing import estimate_cost_usd
from devsper.types.task import Task


class RemoteAgent:
    """Drop-in agent compatible with Executor.run_task signature."""

    def __init__(self, endpoints: list[str], model_name: str = "gpt-4o-mini", timeout_s: float = 120.0):
        if not endpoints:
            raise ValueError("RemoteAgent requires at least one endpoint")
        self._endpoints = [e.rstrip("/") for e in endpoints]
        self._rr = itertools.cycle(self._endpoints)
        self.model_name = model_name
        self.timeout_s = timeout_s

    def run_task(self, task: Task, model_override: str | None = None, prefetch_result=None) -> str:
        endpoint = next(self._rr)
        model = model_override or self.model_name
        req = AgentExecuteRequest(
            task_id=task.id,
            run_id=getattr(task, "run_id", "") or "",
            task=task.description or "",
            context={
                "memory": [],
                "prior_outputs": {},
                "tools_available": [],
            },
            config={"model": model},
            budget_remaining_usd=None,
        )
        t0 = time.perf_counter()
        with httpx.Client(timeout=self.timeout_s) as client:
            resp = client.post(f"{endpoint}/agent/execute", json=req.model_dump())
            resp.raise_for_status()
            body = resp.json()
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        task.result = str(body.get("output", ""))
        task.error = body.get("error")
        tokens = body.get("tokens", {}) or {}
        task.prompt_tokens = int(tokens.get("prompt", 0) or 0)
        task.completion_tokens = int(tokens.get("completion", 0) or 0)
        task.tokens_used = task.prompt_tokens + task.completion_tokens
        task.cost_usd = body.get("cost_usd")
        if task.cost_usd is None:
            task.cost_usd = estimate_cost_usd(model, task.prompt_tokens, task.completion_tokens)
        return task.result
