"""
A2A server: expose devsper agents as A2A-compliant endpoints (FastAPI).
"""

from typing import Any

from devsper.agents.a2a.types import AgentCard, AgentSkill, A2ATaskRequest, A2ATaskResponse


def _build_agent_card(host: str, port: int, swarm_name: str) -> dict:
    """Build AgentCard JSON for GET /.well-known/agent.json."""
    from devsper.intelligence.strategy_selector import ExecutionStrategy
    url = f"http://{host}:{port}"
    name = swarm_name or "devsper"
    skills = [
        {
            "id": s.value,
            "name": s.value.replace("_", " ").title(),
            "description": f"Execute task using {s.value} strategy.",
            "inputModes": ["text"],
            "outputModes": ["text"],
        }
        for s in ExecutionStrategy
        if s != ExecutionStrategy.GENERAL
    ]
    return {
        "name": name,
        "description": "devsper swarm orchestration as A2A agent.",
        "url": url,
        "version": "1.10.5",
        "capabilities": ["streaming"],
        "skills": skills,
    }


def create_a2a_app(host: str = "localhost", port: int = 8080, swarm_name: str = "") -> Any:
    """Create FastAPI app with A2A routes. Requires fastapi, uvicorn, sse-starlette."""
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    import asyncio
    import uuid

    app = FastAPI(title="devsper A2A Server")

    @app.get("/.well-known/agent.json")
    def agent_card() -> dict:
        return _build_agent_card(host, port, swarm_name)

    @app.post("/tasks/send")
    async def tasks_send(body: dict) -> dict:
        """Accept A2A task, run via Swarm, return result."""
        task_id = body.get("id") or str(uuid.uuid4())
        message = body.get("message") or {}
        text = message.get("text", "") if isinstance(message, dict) else ""
        if not text:
            return {
                "id": task_id,
                "status": "failed",
                "result": "Missing message.text",
                "artifacts": [],
            }
        try:
            from devsper.config import get_config
            from devsper.swarm.swarm import Swarm
            cfg = get_config()
            swarm = Swarm(config=cfg)
            result = swarm.run(text)
            out = "\n".join(f"{k}: {v[:2000]}" for k, v in result.items()) if result else ""
            return {
                "id": task_id,
                "status": "completed",
                "result": out,
                "artifacts": [],
            }
        except Exception as e:
            return {
                "id": task_id,
                "status": "failed",
                "result": str(e),
                "artifacts": [],
            }

    @app.post("/tasks/sendSubscribe")
    async def tasks_send_subscribe(body: dict):
        """SSE streaming task execution."""
        task_id = body.get("id") or str(uuid.uuid4())
        message = body.get("message") or {}
        text = message.get("text", "") if isinstance(message, dict) else ""

        async def stream():
            if not text:
                yield f"data: {__import__('json').dumps({'error': 'Missing message.text'})}\n\n"
                return
            try:
                from devsper.config import get_config
                from devsper.swarm.swarm import Swarm
                cfg = get_config()
                swarm = Swarm(config=cfg)
                result = swarm.run(text)
                out = "\n".join(f"{k}: {v[:2000]}" for k, v in result.items()) if result else ""
                yield f"data: {__import__('json').dumps({'id': task_id, 'status': 'completed', 'result': out})}\n\n"
            except Exception as e:
                yield f"data: {__import__('json').dumps({'id': task_id, 'status': 'failed', 'result': str(e)})}\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @app.get("/tasks/{task_id}")
    def task_status(task_id: str) -> dict:
        """Task status (stub: we don't persist task state for now)."""
        return {"id": task_id, "status": "completed", "result": None, "artifacts": []}

    @app.post("/tasks/{task_id}/cancel")
    def task_cancel(task_id: str) -> dict:
        """Cancel running task (stub)."""
        return {"id": task_id, "status": "canceled", "result": None, "artifacts": []}

    return app


def run_a2a_server(host: str = "localhost", port: int = 8080, swarm_name: str = "") -> None:
    """Run A2A server with uvicorn."""
    import uvicorn
    app = create_a2a_app(host=host, port=port, swarm_name=swarm_name)
    uvicorn.run(app, host=host, port=port)
