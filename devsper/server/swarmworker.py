import argparse
import logging
import json
import os
import threading
import queue
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException

from devsper.swarm.swarm import Swarm
from devsper.utils.event_logger import EventLog
from devsper.memory.memory_router import MemoryRouter
from devsper.memory.memory_store import get_default_store
from devsper.memory.memory_index import MemoryIndex
from devsper.config import get_config
from devsper.platform.redis_results_sink import ChainedDevSperSink, RedisEventSink
from devsper.platform.runtime_events import platform_sink_from_env
from pydantic import BaseModel, Field

from devsper.server.memory_utils import close_vektori


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await close_vektori()


app = FastAPI(lifespan=lifespan)
logger = logging.getLogger("swarmworker")


class ExecuteRequest(BaseModel):
    task: str = ""
    run_id: str = "unknown"
    org_id: str = ""
    model: str = ""
    provider: str = ""
    runtime_config: dict = Field(default_factory=dict)
    # NOTE: `model_config` is a reserved pydantic config attribute name.
    # Use a different field name and alias it back to the expected JSON key.
    model_config_data: dict = Field(
        default_factory=dict,
        validation_alias="model_config",
        serialization_alias="model_config",
    )
    execution_mode: str = "distributed"
    worker_type: str = "swarm"
    model_routing_hints: dict = Field(default_factory=dict)
    # Workflow hub (cursor.md): runworker passes these in the JSON body.
    run_type: str = ""
    workflow_template_id: str = ""
    workflow_id: str = ""  # alias; same UUID as template
    entity_key: str = ""
    entity_label: str = ""
    memory_depth: str = "l1"
    inputs: dict[str, Any] = Field(default_factory=dict)
    prompt_template: str = ""
    swarm_config: dict[str, Any] = Field(default_factory=dict)


def _check_internal(authorization: str | None = Header(default=None)) -> None:
    sec = (os.environ.get("PLATFORM_INTERNAL_SECRET") or "").strip()
    if not sec or (authorization or "").strip() != f"Bearer {sec}":
        raise HTTPException(status_code=401, detail="unauthorized")


InternalAuth = Annotated[None, Depends(_check_internal)]


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


def _register_runtime_mcp_servers(runtime_config: dict | None) -> None:
    """Register MCP tools from platform runtime_config (org tool broker)."""
    if not runtime_config:
        return
    raw = runtime_config.get("mcp_servers")
    if not isinstance(raw, list) or not raw:
        return
    try:
        from devsper.config.schema import MCPServerConfig
        from devsper.tools.mcp import register_mcp_server
    except Exception as ex:
        logger.warning("MCP imports unavailable: %s", ex)
        return
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            cfg_mcp = MCPServerConfig.model_validate(item)
            if not (cfg_mcp.name or "").strip():
                continue
            n = register_mcp_server(cfg_mcp)
            logger.info(
                "runtime MCP registered name=%s tools=%d", cfg_mcp.name, n
            )
        except Exception as ex:
            logger.warning("runtime MCP register failed: %s", ex)


def _typed_workflow_runner_envelope(
    *,
    workflow_raw: dict,
    inputs_dict: dict[str, Any],
    selected_model: str,
    selected_provider: str,
    cfg,
    workflow_use_tools: bool,
    workflow_simulation: bool,
    event_log: Any,
    memory_router: Any,
    worker_count: int = 1,
    runtime_config: dict | None = None,
) -> dict[str, Any]:
    """Run WorkflowRunner and return the same envelope shape as the /execute typed-workflow branch."""
    from devsper.workflow.schema import WorkflowDefinition
    from devsper.workflow.runner import WorkflowRunner

    effective_worker_model = (
        "mock"
        if workflow_simulation
        else (selected_model or cfg.worker_model)
    )

    try:
        definition = WorkflowDefinition.model_validate(workflow_raw)
    except Exception as e:
        return {
            "version": 1,
            "status": "failed",
            "provider": selected_provider or "python-swarm",
            "model": effective_worker_model,
            "output": f"WorkflowDefinition validation failed: {e}",
            "usage": {"tokens_in": 0, "tokens_out": 0, "tokens_saved": 0},
            "latency_ms": 0,
            "attempt": 1,
            "dag": {"nodes": [], "edges": []},
        }

    _register_runtime_mcp_servers(runtime_config)

    wc = max(1, min(16, int(worker_count)))

    runner = WorkflowRunner()
    ctx = runner.run(
        workflow=definition,
        inputs=inputs_dict,
        worker_model=effective_worker_model,
        worker_count=wc,
        memory_router=memory_router,
        use_tools=workflow_use_tools,
        event_log=event_log,
    )

    ordered_ids = [s.id for s in definition.steps]
    steps_by_id = {sid: ctx.steps.get(sid) for sid in ordered_ids}

    has_error = any(
        (sr is not None and (not sr.skipped) and sr.error) for sr in steps_by_id.values()
    )

    nodes = []
    edges = []
    for step in definition.steps:
        label = (step.task or "").strip().splitlines()[0][:46] if step.task else step.id
        nodes.append({"id": step.id, "label": label, "type": "task"})
        for dep in (step.depends_on or []):
            edges.append({"id": f"e_{dep}_to_{step.id}", "source": dep, "target": step.id})

    dag_data = {"nodes": nodes, "edges": edges}

    ordered_step_results = []
    last_raw = ""
    for sid in ordered_ids:
        sr = steps_by_id.get(sid)
        if sr is None:
            continue
        if sr.raw_result:
            last_raw = sr.raw_result
        ordered_step_results.append(
            {
                "step_id": sr.step_id,
                "skipped": sr.skipped,
                "error": sr.error,
                "raw_result": sr.raw_result,
                "structured": sr.structured,
                "duration_seconds": sr.duration_seconds,
            }
        )

    combined_output = last_raw or "\n".join(
        [str(s.get("raw_result") or "") for s in ordered_step_results if s.get("raw_result")]
    )[:5000]

    return {
        "version": 1,
        "status": "failed" if has_error else "completed",
        "provider": selected_provider or "python-swarm",
        "model": effective_worker_model,
        "output": combined_output,
        "usage": {"tokens_in": 0, "tokens_out": 0, "tokens_saved": 0},
        "latency_ms": 0,
        "attempt": 1,
        "dag": dag_data,
        "steps": ordered_step_results,
        "workflow": {
            "name": definition.name,
            "description": definition.description,
            "version": definition.version,
        },
    }


def _execute_workflow_hub_typed(
    data: dict,
    r,
    cfg,
    sink: object,
    run_id: str,
    selected_model: str,
    selected_provider: str,
    runtime_config: dict,
) -> dict[str, Any]:
    """Hub run with compiled WorkflowDefinition + Vektori memory (entity_key)."""
    from devsper.server.memory_utils import (
        format_workflow_memory_context,
        messages_from_swarm_result,
        persist_workflow_run_memory,
        update_namespace_stats,
    )
    from devsper.memory.memory_router import MemoryRouter
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex

    wf_tid = str(data.get("workflow_template_id") or data.get("workflow_id") or "").strip()
    ek = str(data.get("entity_key") or "").strip()
    mem_depth = str(data.get("memory_depth") or "l1").strip() or "l1"
    inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
    task_seed = str(data.get("task") or "").strip()
    workflow_raw = runtime_config.get("devsper_workflow")
    if not isinstance(workflow_raw, dict):
        return _execute_workflow_hub(
            data, r, cfg, sink, run_id, selected_model, selected_provider
        )

    workflow_inputs = runtime_config.get("devsper_workflow_inputs")
    if not isinstance(workflow_inputs, dict):
        workflow_inputs = inputs
    workflow_use_tools = bool(runtime_config.get("devsper_workflow_use_tools"))

    q_for_mem = task_seed or json.dumps(workflow_inputs, ensure_ascii=False)[:800]
    memory_ctx = ""
    try:
        memory_ctx = format_workflow_memory_context(wf_tid, ek, q_for_mem, mem_depth, top_k=10)
    except Exception as ex:
        logger.warning("Vektori memory inject skipped (typed hub): %s", ex)

    inputs_merged = dict(workflow_inputs)
    inputs_merged["memory"] = memory_ctx

    sc = data.get("swarm_config") if isinstance(data.get("swarm_config"), dict) else {}
    try:
        worker_count = max(1, min(16, int(sc.get("workers", 2))))
    except (TypeError, ValueError):
        worker_count = 2

    event_log = EventLog(
        events_folder_path=cfg.events_dir, run_id=run_id, platform_sink=sink
    )
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )

    envelope = _typed_workflow_runner_envelope(
        workflow_raw=workflow_raw,
        inputs_dict=inputs_merged,
        selected_model=selected_model,
        selected_provider=selected_provider,
        cfg=cfg,
        workflow_use_tools=workflow_use_tools,
        workflow_simulation=False,
        event_log=event_log,
        memory_router=memory_router,
        worker_count=worker_count,
        runtime_config=runtime_config,
    )

    status = str(envelope.get("status") or "completed")
    steps_list = envelope.get("steps") if isinstance(envelope.get("steps"), list) else []
    results: dict[str, str] = {}
    for s in steps_list:
        if isinstance(s, dict) and s.get("step_id"):
            results[str(s["step_id"])] = str(s.get("raw_result") or "")

    facts_written = 0
    try:
        msgs = messages_from_swarm_result(task_seed or "workflow", results if results else None)
        facts_written = persist_workflow_run_memory(wf_tid, ek, run_id, msgs)
        update_namespace_stats(wf_tid, ek, run_id)
    except Exception as ex:
        logger.warning("Vektori persist skipped (typed hub): %s", ex)

    agent_trace = [
        {"name": "WorkflowRunner", "status": "completed" if status == "completed" else "failed", "duration_s": 0},
        {
            "name": "Steps",
            "status": "failed" if status == "failed" else "completed",
            "duration_s": 0,
            "detail": (str(envelope.get("output") or "")[:500] if status == "failed" else ""),
        },
    ]
    envelope["facts_written"] = facts_written
    envelope["agent_trace"] = agent_trace
    envelope["memory_written_summary"] = (
        f"{facts_written} facts saved to namespace before completion."
        if facts_written
        else "No new memory facts extracted for this run."
    )
    return envelope


def _execute_workflow_hub(
    data: dict,
    r,
    cfg,
    sink: object,
    run_id: str,
    selected_model: str,
    selected_provider: str,
) -> dict[str, Any]:
    """Swarm run with Vektori inject + persist; devsper runtime memory disabled."""
    from pathlib import Path

    from devsper.server.memory_utils import (
        apply_prompt_template,
        format_workflow_memory_context,
        messages_from_swarm_result,
        persist_workflow_run_memory,
        update_namespace_stats,
    )

    wf = str(data.get("workflow_template_id") or data.get("workflow_id") or "").strip()
    ek = str(data.get("entity_key") or "").strip()
    mem_depth = str(data.get("memory_depth") or "l1").strip() or "l1"
    inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
    tmpl = str(data.get("prompt_template") or "").strip()
    sc = data.get("swarm_config") if isinstance(data.get("swarm_config"), dict) else {}
    task_seed = str(data.get("task") or "").strip()

    q_for_mem = task_seed or tmpl or json.dumps(inputs, ensure_ascii=False)[:800]
    memory_ctx = ""
    try:
        memory_ctx = format_workflow_memory_context(wf, ek, q_for_mem, mem_depth, top_k=10)
    except Exception as ex:
        logger.warning("Vektori memory inject skipped: %s", ex)

    if tmpl:
        full_prompt = apply_prompt_template(tmpl, inputs, memory_ctx)
    else:
        full_prompt = (task_seed or "Run workflow") + (
            f"\n\n{memory_ctx}" if memory_ctx else ""
        )

    event_log = EventLog(
        events_folder_path=cfg.events_dir, run_id=run_id, platform_sink=sink
    )

    try:
        workers = max(1, min(16, int(sc.get("workers", 2))))
    except (TypeError, ValueError):
        workers = 2
    wm = str(sc.get("worker_model") or "").strip() or selected_model or cfg.worker_model
    pm = str(sc.get("planner_model") or "").strip() or selected_model or cfg.planner_model
    use_tools = bool(sc.get("use_tools", True))

    clarification_queue = queue.Queue()
    swarm = Swarm(
        worker_count=workers,
        worker_model=wm,
        planner_model=pm,
        event_log=event_log,
        memory_router=None,
        store_swarm_memory=False,
        use_tools=use_tools,
        clarification_queue=clarification_queue,
    )
    stop_event = threading.Event()
    t = threading.Thread(
        target=hitl_bridge_thread,
        args=(r, run_id, clarification_queue, swarm, stop_event, sink),
        daemon=True,
    )
    t.start()
    results = None
    err_text = ""
    try:
        results = swarm.run(full_prompt)
    except Exception as ex:
        err_text = str(ex)
        logger.exception("workflow hub swarm failed run_id=%s", run_id)
    finally:
        stop_event.set()
        t.join(timeout=1.0)

    dag_data: dict = {}
    dag_path = Path(cfg.events_dir) / f"{run_id}_dag.json"
    if dag_path.exists():
        try:
            dag_data = json.loads(dag_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    combined_output = ""
    if results:
        combined_output = "\n".join([f"{k}: {v}" for k, v in results.items()])
    status = "failed" if err_text else "completed"
    if err_text:
        combined_output = combined_output or err_text

    facts_written = 0
    try:
        msgs = messages_from_swarm_result(full_prompt, results)
        facts_written = persist_workflow_run_memory(wf, ek, run_id, msgs)
        update_namespace_stats(wf, ek, run_id)
    except Exception as ex:
        logger.warning("Vektori persist skipped: %s", ex)

    agent_trace = [
        {"name": "Planner", "status": "completed", "duration_s": 0},
        {
            "name": "Executor",
            "status": "failed" if err_text else "completed",
            "duration_s": 0,
            "detail": (err_text[:500] if err_text else ""),
        },
    ]
    envelope: dict[str, Any] = {
        "version": 1,
        "status": status,
        "provider": selected_provider or "python-swarm",
        "model": wm,
        "output": (combined_output[:20000] if combined_output else ""),
        "usage": {"tokens_in": 0, "tokens_out": 0, "tokens_saved": 0},
        "latency_ms": 0,
        "attempt": 1,
        "dag": dag_data,
        "facts_written": facts_written,
        "agent_trace": agent_trace,
        "memory_written_summary": (
            f"{facts_written} facts saved to namespace before completion."
            if facts_written
            else "No new memory facts extracted for this run."
        ),
    }
    if err_text:
        envelope["error"] = {
            "message": err_text[:2000],
            "code": "workflow_execution_error",
        }
    return envelope


@app.post("/execute")
def execute(req: ExecuteRequest):
    data = req.model_dump(by_alias=True)
    from devsper.platform.run_context import clear_execution_org, set_execution_org

    set_execution_org(str(data.get("org_id") or ""))
    try:
        return _execute_dispatch(data)
    finally:
        clear_execution_org()


def _execute_dispatch(data: dict[str, Any]) -> dict[str, Any]:
    task = data.get("task", "")
    run_id = data.get("run_id", "unknown")
    runtime_config = data.get("runtime_config") or {}
    model_config = data.get("model_config") or {}
    execution_mode = (data.get("execution_mode") or "distributed").strip() or "distributed"
    worker_type = (data.get("worker_type") or "swarm").strip() or "swarm"
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
        "Executing swarm for run %s model=%s provider=%s mode=%s worker_type=%s",
        run_id,
        selected_model or "(default)",
        selected_provider or "(default)",
        execution_mode,
        worker_type,
    )

    import redis

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    results_sink = RedisEventSink(r, f"devsper:results:{run_id}")
    cfg = get_config()
    fwd = platform_sink_from_env(cfg.events_dir, run_id_override=run_id)
    sink: object = (
        ChainedDevSperSink([results_sink, fwd]) if fwd is not None else results_sink
    )

    rt = (data.get("run_type") or "").strip().lower()
    wf_tid = str(data.get("workflow_template_id") or data.get("workflow_id") or "").strip()
    ek = str(data.get("entity_key") or "").strip()
    if rt == "workflow" and wf_tid and ek:
        if isinstance(runtime_config.get("devsper_workflow"), dict):
            return _execute_workflow_hub_typed(
                data,
                r,
                cfg,
                sink,
                run_id,
                selected_model,
                selected_provider,
                runtime_config,
            )
        return _execute_workflow_hub(
            data, r, cfg, sink, run_id, selected_model, selected_provider
        )

    event_log = EventLog(
        events_folder_path=cfg.events_dir, run_id=run_id, platform_sink=sink
    )

    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(get_default_store()),
        top_k=5,
    )

    # Optional: execute a typed WorkflowDefinition instead of swarm.run(task).
    # The platform passes it in runtime_config as `devsper_workflow`.
    workflow_raw = runtime_config.get("devsper_workflow")
    workflow_inputs = runtime_config.get("devsper_workflow_inputs")
    workflow_simulation = bool(runtime_config.get("devsper_workflow_simulation"))
    workflow_use_tools = bool(runtime_config.get("devsper_workflow_use_tools"))

    if isinstance(workflow_raw, dict):
        inputs_dict = workflow_inputs if isinstance(workflow_inputs, dict) else {}
        return _typed_workflow_runner_envelope(
            workflow_raw=workflow_raw,
            inputs_dict=inputs_dict,
            selected_model=selected_model,
            selected_provider=selected_provider,
            cfg=cfg,
            workflow_use_tools=workflow_use_tools,
            workflow_simulation=workflow_simulation,
            event_log=event_log,
            memory_router=memory_router,
            worker_count=1,
            runtime_config=runtime_config,
        )

    clarification_queue = queue.Queue()

    swarm = Swarm(
        worker_count=2,
        worker_model=selected_model or cfg.worker_model,
        planner_model=selected_model or cfg.planner_model,
        event_log=event_log,
        memory_router=None,
        store_swarm_memory=False,
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


class MemorySearchBody(BaseModel):
    query: str = ""
    depth: str = "l1"
    limit: int = 20


class MemoryAddBody(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str | None = None


@app.get("/internal/memory/namespaces/{workflow_template_id}")
def internal_memory_namespaces(workflow_template_id: str, _auth: InternalAuth):
    from psycopg import connect
    from psycopg.rows import dict_row

    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        raise HTTPException(status_code=503, detail="database_unconfigured")
    with connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text, entity_key, entity_label, fact_count,
                       last_run_id::text, updated_at
                FROM workflow_memory_namespaces
                WHERE workflow_template_id = %s::uuid
                ORDER BY updated_at DESC
                """,
                (workflow_template_id,),
            )
            rows = cur.fetchall()
    return {"namespaces": rows}


@app.post("/internal/memory/{workflow_template_id}/{entity_key}/search")
def internal_memory_search(
    workflow_template_id: str,
    entity_key: str,
    body: MemorySearchBody,
    _auth: InternalAuth,
):
    from devsper.server.memory_utils import search_workflow_memory

    try:
        res = search_workflow_memory(
            workflow_template_id,
            entity_key,
            body.query,
            body.depth or "l1",
            min(50, max(1, body.limit)),
        )
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex
    return {"results": res}


@app.post("/internal/memory/{workflow_template_id}/{entity_key}/add")
def internal_memory_add(
    workflow_template_id: str,
    entity_key: str,
    body: MemoryAddBody,
    _auth: InternalAuth,
):
    from devsper.server.memory_utils import add_memory_manually_sync, update_namespace_stats

    sid = body.session_id or f"manual:{uuid.uuid4()}"
    try:
        n = add_memory_manually_sync(
            workflow_template_id,
            entity_key,
            body.messages,
            session_id=sid,
        )
        update_namespace_stats(workflow_template_id, entity_key, sid)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex)) from ex
    return {"ok": True, "facts_written": n}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
