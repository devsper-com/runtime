from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from devsper.server.topology import list_runs, topology_snapshot
from devsper.types.event import Event


def create_events_app(events_dir: str):
    try:
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse, StreamingResponse
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Install server extras: pip install devsper[server]") from exc

    app = FastAPI(title="devsper-events-api", version="1.0")

    @app.get("/runs")
    def runs():
        return list_runs(events_dir)

    @app.get("/runs/{run_id}")
    def run_detail(run_id: str):
        return topology_snapshot(events_dir, run_id)

    @app.get("/runs/{run_id}/topology")
    def run_topology(run_id: str):
        return topology_snapshot(events_dir, run_id)

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str):
        p = Path(events_dir) / f"{run_id}.jsonl"

        async def _gen():
            pos = 0
            while True:
                if p.exists():
                    data = p.read_text(encoding="utf-8")
                    if pos < len(data):
                        chunk = data[pos:]
                        pos = len(data)
                        for ln in chunk.splitlines():
                            ln = ln.strip()
                            if not ln:
                                continue
                            try:
                                ev = Event.model_validate_json(ln)
                                payload = {
                                    "event": ev.type.value.replace("_", "."),
                                    "run_id": run_id,
                                    "task_id": (ev.payload or {}).get("task_id"),
                                    "timestamp": ev.timestamp.isoformat(),
                                    "data": ev.payload or {},
                                }
                                import json

                                yield f"data: {json.dumps(payload)}\n\n"
                            except Exception:
                                continue
                await asyncio.sleep(1.0)

        return StreamingResponse(_gen(), media_type="text/event-stream")

    return app


def serve_api(port: int = 7474, host: str = "0.0.0.0", events_dir: str = ".devsper/events") -> int:
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Install server extras: pip install devsper[server]") from exc
    uvicorn.run(create_events_app(events_dir), host=host, port=port)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve devsper live events/topology API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7474)
    parser.add_argument("--events-dir", default=".devsper/events")
    args = parser.parse_args()
    return serve_api(port=args.port, host=args.host, events_dir=args.events_dir)
