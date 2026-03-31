import argparse
import logging
import json
import threading
import queue
import time
from datetime import datetime, timezone
from fastapi import FastAPI
import uvicorn

from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog
from devsper.memory.memory_router import MemoryRouter
from devsper.memory.memory_store import get_default_store
from devsper.memory.memory_index import MemoryIndex
from devsper.config import get_config
from devsper.platform.redis_results_sink import ChainedDevSperSink, RedisEventSink
from devsper.platform.runtime_events import platform_sink_from_env
from pydantic import BaseModel, Field

app = FastAPI()
logger = logging.getLogger("swarmworker")


class ExecuteRequest(BaseModel):
    task: str
    run_id: str = "unknown"
    org_id: str = ""
    model: str = ""
    provider: str = ""
    runtime_config: dict = Field(default_factory=dict)
    model_routing_hints: dict = Field(default_factory=dict)


def hitl_bridge_thread(
    redis_client, run_id, clarification_queue, swarm_ref, stop_event, event_sink
):
    """Bridges requests from swarm to Redis, and answers from Redis to swarm."""
    from devsper.events import ClarificationResponse
    from devsper.types.event import Event, events as event_types

    pubsub = redis_client.pubsub()
    input_channel = f"devsper:inputs:{run_id}"
    pubsub.subscribe(input_channel)

    last_empty_at = time.monotonic()
    while not stop_event.is_set():
        # Check for outbound clarification requests from the swarm
        try:
            req = clarification_queue.get_nowait()

            # Emit real platform-mappable event so UI can render HITL prompt.
            event_sink.on_devsper_event(
                Event(
                    timestamp=datetime.now(timezone.utc),
                    type=event_types.CLARIFICATION_REQUESTED,
                    payload=req.to_dict() if hasattr(req, "to_dict") else {},
                )
            )
            field_count = len(getattr(req, "fields", []) or [])
            logger.info(
                "Published clarification request %s to Redis (fields=%d, task_id=%s)",
                req.request_id,
                field_count,
                getattr(req, "task_id", ""),
            )

        except queue.Empty:
            # Avoid spamming logs, but keep some signal when runs are stuck.
            now = time.monotonic()
            if now - last_empty_at > 15:
                logger.debug(
                    "HITL bridge waiting for clarification requests (run_id=%s)",
                    run_id,
                )
                last_empty_at = now

        # Check for inbound answers from the platform
        msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg and msg["type"] == "message":
            try:
                data = json.loads(msg["data"])
                req_id = data.get("request_id")
                answers = data.get("answers") or {}
                skipped = bool(data.get("skipped", False))
                if req_id and swarm_ref and swarm_ref._current_executor:
                    logger.info(f"Received HITL answer for {req_id} (skipped={skipped})")
                    resp = ClarificationResponse(
                        request_id=req_id, answers=answers, skipped=skipped
                    )
                    swarm_ref._current_executor.receive_clarification(resp)
            except Exception as e:
                logger.error(f"Failed to process HITL input: {e}")


@app.post("/execute")
def execute(req: ExecuteRequest):
    data = req.model_dump()
    task = data.get("task", "")
    run_id = data.get("run_id", "unknown")
    runtime_config = data.get("runtime_config") or {}
    model_hints = data.get("model_routing_hints") or {}
    selected_model = (
        (data.get("model") or "").strip()
        or (model_hints.get("model") or "").strip()
        or (runtime_config.get("model") or "").strip()
    )
    selected_provider = (
        (data.get("provider") or "").strip()
        or (model_hints.get("provider") or "").strip()
        or (runtime_config.get("provider") or "").strip()
    )

    logger.info(
        "Executing swarm for run %s model=%s provider=%s",
        run_id,
        selected_model or "(default)",
        selected_provider or "(default)",
    )

    import redis
    import os

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    results_sink = RedisEventSink(r, f"devsper:results:{run_id}")
    cfg = get_config()
    fwd = platform_sink_from_env(cfg.events_dir, run_id_override=run_id)
    sink: object = (
        ChainedDevSperSink([results_sink, fwd]) if fwd is not None else results_sink
    )

    event_log = EventLog(
        events_folder_path=cfg.events_dir, run_id=run_id, platform_sink=sink
    )

    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )

    clarification_queue = queue.Queue()

    swarm = Swarm(
        worker_count=2,
        worker_model=selected_model or cfg.worker_model,
        planner_model=selected_model or cfg.planner_model,
        event_log=event_log,
        memory_router=memory_router,
        use_tools=True,
        clarification_queue=clarification_queue,
    )

    stop_event = threading.Event()
    t = threading.Thread(
        target=hitl_bridge_thread,
        args=(r, run_id, clarification_queue, swarm, stop_event, sink),
        daemon=True,
    )
    t.start()

    try:
        results = swarm.run(task)
    finally:
        stop_event.set()
        t.join(timeout=1.0)

    # Try to load the DAG saved by swarm
    from pathlib import Path

    dag_data = {}
    dag_path = Path(cfg.events_dir) / f"{run_id}_dag.json"
    if dag_path.exists():
        try:
            dag_data = json.loads(dag_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Format the result similar to the Go worker's envelope
    combined_output = ""
    if results:
        combined_output = "\n".join([f"{k}: {v}" for k, v in results.items()])

    envelope = {
        "version": 1,
        "status": "completed",
        "provider": selected_provider or "python-swarm",
        "model": selected_model or cfg.worker_model,
        "output": combined_output,
        "usage": {
            "tokens_in": 0,
            "tokens_out": 0,
            "tokens_saved": 0,
        },
        "latency_ms": 0,
        "attempt": 1,
        "dag": dag_data,
    }

    # Go worker expects the return body to be the ResultEnvelope?
    # Actually, the Go worker will parse our response.
    return envelope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
