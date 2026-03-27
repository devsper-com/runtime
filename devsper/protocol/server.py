"""FastAPI server implementing the devsper polyglot agent protocol."""

from __future__ import annotations

import argparse
import time

from devsper.agents.agent import Agent
from devsper.protocol.schema import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    AgentExecuteTokens,
    ToolCallRecord,
)
from devsper.telemetry.pricing import estimate_cost_usd
from devsper.types.task import Task


def create_protocol_app(agent: Agent | None = None):
    try:
        from fastapi import FastAPI
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Install server extras: pip install devsper[server]") from exc

    a = agent or Agent(use_tools=True)
    app = FastAPI(title="devsper-protocol", version="1.0")

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "1.0", "runtime": "python"}

    @app.get("/agent")
    def agent_info():
        return {"name": "devsper-python-agent", "capabilities": ["task.execute", "tools"], "models": [a.model_name]}

    @app.post("/agent/execute", response_model=AgentExecuteResponse)
    def execute(req: AgentExecuteRequest):
        t0 = time.perf_counter()
        task = Task(id=req.task_id, description=req.task, dependencies=[])
        out = a.run_task(task, model_override=req.config.model)
        prompt_tokens = int(getattr(task, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(task, "completion_tokens", 0) or 0)
        cost = getattr(task, "cost_usd", None)
        if cost is None:
            cost = estimate_cost_usd(req.config.model, prompt_tokens, completion_tokens)
        return AgentExecuteResponse(
            task_id=req.task_id,
            output=out or "",
            tool_calls=[],
            tokens=AgentExecuteTokens(prompt=prompt_tokens, completion=completion_tokens),
            cost_usd=cost,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            error=getattr(task, "error", None),
        )

    return app


def serve(host: str = "0.0.0.0", port: int = 8080) -> int:
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("Install server extras: pip install devsper[server]") from exc
    app = create_protocol_app()
    uvicorn.run(app, host=host, port=port)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve devsper polyglot agent protocol")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    return serve(args.host, args.port)
