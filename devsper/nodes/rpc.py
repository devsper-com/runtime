"""
RPC layer: FastAPI server for health, status, snapshot, control, SSE event stream.
Distributed mode only; requires fastapi, uvicorn.
"""

import asyncio
import json
import logging
from typing import Any, Callable

log = logging.getLogger(__name__)


def _require_distributed() -> None:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "RPC requires: pip install devsper[distributed]"
        ) from e


def create_rpc_app(
    node_id: str,
    role: str,
    get_status: Callable[[], Any],
    get_current_tasks: Callable[[], list] | None = None,
    get_snapshot: Callable[[], Any] | None = None,
    rpc_token: str | None = None,
    event_stream_callback: Callable[[], object] | None = None,
    controller_publish: Callable[[str, dict], object] | None = None,
) -> object:
    """Create FastAPI app for node RPC endpoints."""
    _require_distributed()
    from fastapi import FastAPI, Request, Response, Depends, Header
    from fastapi.responses import StreamingResponse
    import time
    app = FastAPI(title="devsper Node RPC")
    _start = time.monotonic()

    def _check_token(
        x_devsper_token: str | None = Header(None, alias="X-devsper-Token"),
        authorization: str | None = Header(None),
    ):
        if not rpc_token:
            return
        token = x_devsper_token or (authorization.replace("Bearer ", "").strip() if authorization else None)
        if token != rpc_token:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Invalid or missing X-devsper-Token")

    @app.get("/health")
    async def health():
        return {
            "node_id": node_id,
            "role": role,
            "healthy": True,
            "uptime_seconds": time.monotonic() - _start,
            "version": _get_version(),
        }

    @app.get("/status")
    async def status():
        s = get_status()
        if asyncio.iscoroutine(s):
            return await s
        return s

    @app.get("/tasks")
    async def tasks():
        if get_current_tasks is None:
            return []
        return get_current_tasks()

    @app.get("/snapshot", dependencies=[Depends(_check_token)])
    async def snapshot():
        if get_snapshot is None:
            return {"error": "Not a controller"}
        snap = get_snapshot()
        if asyncio.iscoroutine(snap):
            snap = await snap
        return snap

    @app.post("/control", dependencies=[Depends(_check_token)])
    async def control(request: Request):
        body = await request.json()
        command = body.get("command")
        target = body.get("target", "all")
        if controller_publish:
            controller_publish("swarm.control", {"command": command, "target": target})
        return {"ok": True}

    @app.get("/stream/events")
    async def stream_events():
        if event_stream_callback is None:
            async def empty():
                yield "data: {}\n\n"
            return StreamingResponse(empty(), media_type="text/event-stream")
        async def gen():
            # Placeholder: in real impl, subscribe to bus and yield SSE
            while True:
                try:
                    yield f"data: {json.dumps({'t': 'ping'})}\n\n"
                except asyncio.CancelledError:
                    break
                await asyncio.sleep(5)
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def _get_version() -> str:
    try:
        import devsper
        return getattr(devsper, "__version__", "1.10.0")
    except Exception:
        return "1.10.0"


async def run_rpc_server(app: object, port: int = 7700, host: str = "0.0.0.0") -> None:
    """Run uvicorn server in process (non-blocking via create_task)."""
    _require_distributed()
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
