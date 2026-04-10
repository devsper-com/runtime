"""
devsper CLI: run, tui, research, analyze, memory, init, doctor, build.

Usage:
    devsper run "analyze diffusion models"
    devsper build "fastapi todo app"
    devsper init
    devsper doctor
    devsper tui
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import importlib
from datetime import datetime, timezone
from pathlib import Path


def _load_project_dotenv() -> None:
    """Load .env from the project directory (where devsper.toml lives) so API keys are available."""
    try:
        from dotenv import load_dotenv
        from devsper.config.config_loader import project_config_paths

        for p in project_config_paths():
            if p.is_file():
                load_dotenv(p.parent / ".env")
                break
    except Exception:
        pass


def _project_root() -> Path:
    """Project root (examples/ parent) for running example scripts."""
    return Path(__file__).resolve().parent.parent.parent


def _import_pool_submodule(submodule: str):
    """Import ``devsper.pool.<submodule>`` (distributed worker pool; lives in the runtime package)."""
    return importlib.import_module(f"devsper.pool.{submodule}")


def _resolve_pool_redis_url(
    cli_override: str | None = None, profile: str | None = None
) -> str:
    """Same Redis URL for pool start, `devsper run` (local profile), and `devsper pool status`."""
    if cli_override:
        return cli_override
    if os.environ.get("REDIS_URL"):
        return os.environ["REDIS_URL"]
    prof = (profile or os.environ.get("DEVSPER_PROFILE") or "").strip().lower()
    if prof == "local":
        try:
            config_mod = _import_pool_submodule("config")
            return config_mod.load_pool_config("local").redis_url
        except Exception:
            return "redis://127.0.0.1:6379"
    # Default for tooling (avoid loading prod.toml which points at non-local Redis).
    return "redis://127.0.0.1:6379"


def _run_example(script_path: Path, *args: str) -> int:
    """Run an example script with project root on PYTHONPATH."""
    root = _project_root()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, str(script_path)] + list(args)
    return subprocess.run(cmd, cwd=str(root), env=env).returncode


def _conversion_events_path() -> Path:
    data_dir = os.environ.get("DEVSPER_DATA_DIR", ".devsper")
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / "conversion_events.jsonl"


def _track_conversion_event(name: str, payload: dict | None = None) -> None:
    try:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": name,
            "payload": payload or {},
        }
        with _conversion_events_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def _count_conversion_events(name: str) -> int:
    p = _conversion_events_path()
    if not p.exists():
        return 0
    count = 0
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if str(row.get("event", "")) == name:
                count += 1
    except Exception:
        return 0
    return count


def _platform_api_builder():
    from devsper.credentials.store import CredentialStore
    from devsper.platform.request_builder import PlatformAPIRequestBuilder

    cs = CredentialStore()
    base_url = (
        os.environ.get("DEVSPER_PLATFORM_API_URL")
        or cs.get("platform", "api_url")
        or ""
    )
    org = os.environ.get("DEVSPER_PLATFORM_ORG") or cs.get("platform", "org") or ""
    token = (
        os.environ.get("DEVSPER_PLATFORM_TOKEN") or cs.get("platform", "token") or ""
    )
    return PlatformAPIRequestBuilder(base_url=base_url, org_slug=org, token=token)


def _extract_platform_run_fields(payload: dict) -> tuple[str, str, int, int, int]:
    status = str(payload.get("status", ""))
    run_id = str(payload.get("run_id", ""))
    tin = int(payload.get("tokens_in", 0) or 0)
    tout = int(payload.get("tokens_out", 0) or 0)
    tsave = int(payload.get("tokens_saved", 0) or 0)
    return run_id, status, tin, tout, tsave


def _run_platform_once(task: str, args: object) -> tuple[int, dict, float]:
    from devsper.platform.request_builder import PlatformAPIError

    api = _platform_api_builder()
    if not api.enabled():
        print(
            "Cloud routing is not configured. Run `devsper platform connect` first.",
            file=sys.stderr,
        )
        return 2, {}, 0.0
    project_id = getattr(args, "project_id", None)
    manifest_path = (getattr(args, "manifest_file", "") or "").strip()
    manifest = {}
    if manifest_path:
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Invalid manifest file: {e}", file=sys.stderr)
            return 2, {}, 0.0
    started = time.time()
    try:
        created = api.create_run(
            task=task, project_id=project_id or "", manifest=manifest
        )
        run_id = str(created.get("run_id", "") or "")
        poll_interval = float(getattr(args, "platform_poll_interval", 2.0) or 2.0)
        if poll_interval <= 0:
            poll_interval = 2.0
        last_print_status = {"status": ""}

        def _on_update(payload: dict, elapsed: float, changed: bool) -> None:
            if getattr(args, "quiet", False):
                return
            status = str(payload.get("status") or "").strip().lower() or "unknown"
            if changed or status != last_print_status["status"]:
                last_print_status["status"] = status
                print(f"[platform] run_id={run_id} status={status} elapsed={elapsed:.1f}s")

        final = api.poll_run(
            run_id,
            interval_seconds=poll_interval,
            timeout_seconds=float(getattr(args, "platform_timeout", 180.0)),
            on_update=_on_update,
        )
        elapsed = time.time() - started
        return 0, final or {}, elapsed
    except TimeoutError as e:
        print(str(e), file=sys.stderr)
        return 1, {}, time.time() - started
    except PlatformAPIError as e:
        print(f"Platform API error: {e}", file=sys.stderr)
        if getattr(e, "body", None):
            print(str(e.body), file=sys.stderr)
        return 1, {}, time.time() - started
    except Exception as e:
        print(f"Platform run failed: {e}", file=sys.stderr)
        return 1, {}, time.time() - started


def _run_platform_only(args: object) -> int:
    task = getattr(args, "task", "Summarize swarm intelligence in one paragraph.")
    _track_conversion_event("platform_run_started", {"mode": "platform_only"})
    code, payload, elapsed = _run_platform_once(task, args)
    if code != 0:
        _track_conversion_event("platform_run_failed", {"mode": "platform_only"})
        return code
    run_id, status, tin, tout, tsave = _extract_platform_run_fields(payload)
    out = {
        "run_id": run_id,
        "status": status,
        "latency_seconds": round(elapsed, 3),
        "tokens_in": tin,
        "tokens_out": tout,
        "tokens_saved": tsave,
        "platform": True,
    }
    if getattr(args, "json_output", False):
        print(json.dumps(out))
    else:
        print(f"[platform] run_id={run_id} status={status} latency={elapsed:.2f}s")
        if tin or tout or tsave:
            print(
                f"[platform] usage tokens_in={tin} tokens_out={tout} tokens_saved={tsave}"
            )
    if _count_conversion_events("first_platform_run") == 0:
        _track_conversion_event(
            "first_platform_run", {"run_id": run_id, "status": status}
        )
        print(
            "Suggestion: next step -> `devsper platform connect --show-roi` or create a project/team invite."
        )
    else:
        _track_conversion_event(
            "second_platform_run", {"run_id": run_id, "status": status}
        )
    return 0 if status == "completed" else 1


def _run_shadow_mode(args: object) -> int:
    task = getattr(args, "task", "Summarize swarm intelligence in one paragraph.")
    _track_conversion_event("platform_shadow_started", {"task_len": len(task)})

    # Local runtime path executed via subprocess to avoid code-path drift.
    local_cmd = [
        sys.executable,
        "-m",
        "devsper.cli.main",
        "run",
        task,
        "--quiet",
        "--json",
    ]
    local_started = time.time()
    local_proc = subprocess.run(local_cmd, capture_output=True, text=True)
    local_elapsed = time.time() - local_started
    local_out = (local_proc.stdout or "").strip()
    local_score = len(local_out)

    p_code, p_payload, p_elapsed = _run_platform_once(task, args)
    run_id, p_status, tin, tout, tsave = _extract_platform_run_fields(p_payload)
    reliability_runtime = 1 if local_proc.returncode == 0 else 0
    reliability_platform = 1 if p_code == 0 and p_status == "completed" else 0
    quality_platform = len(json.dumps(p_payload, default=str))

    print("Shadow run comparison")
    print(
        f"- runtime:  status={'ok' if reliability_runtime else 'failed'} latency={local_elapsed:.2f}s quality_score={local_score}"
    )
    print(
        f"- platform: status={'ok' if reliability_platform else p_status or 'failed'} latency={p_elapsed:.2f}s quality_score={quality_platform}"
    )
    if tin or tout or tsave:
        print(
            f"- platform usage: tokens_in={tin} tokens_out={tout} tokens_saved={tsave}"
        )
    if run_id:
        print(f"- platform run_id: {run_id}")

    _track_conversion_event(
        "platform_shadow_completed",
        {
            "runtime_ok": reliability_runtime,
            "platform_ok": reliability_platform,
            "runtime_latency_s": round(local_elapsed, 3),
            "platform_latency_s": round(p_elapsed, 3),
            "platform_run_id": run_id,
        },
    )
    if local_proc.returncode != 0:
        err = (local_proc.stderr or "").strip()
        if err:
            print(f"[runtime stderr] {err}", file=sys.stderr)
    return 0 if reliability_runtime and reliability_platform else 1


def _upsert_project_platform_memory_config(api_url: str, org_slug: str) -> None:
    path = Path.cwd() / "devsper.toml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if "[memory]" not in text:
        text = text.rstrip() + "\n\n[memory]\n"
    if "backend = " in text and "[memory]" in text:
        text = text.replace('backend = "local"', 'backend = "hybrid"')
    if "platform_api_url" in text:
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("platform_api_url"):
                lines.append(f'platform_api_url = "{api_url}"')
            elif line.strip().startswith("platform_org_slug"):
                lines.append(f'platform_org_slug = "{org_slug}"')
            else:
                lines.append(line)
        text = "\n".join(lines) + "\n"
    else:
        text = (
            text.rstrip()
            + f'\nplatform_api_url = "{api_url}"\nplatform_org_slug = "{org_slug}"\nbackend = "hybrid"\n'
        )
    path.write_text(text, encoding="utf-8")


def _run_platform_connect(args: object) -> int:
    from devsper.credentials.store import CredentialStore
    from devsper.platform.request_builder import PlatformAPIRequestBuilder

    cs = CredentialStore()
    api_url = (
        getattr(args, "api_url", None)
        or os.environ.get("DEVSPER_PLATFORM_API_URL")
        or cs.get("platform", "api_url")
        or ""
    ).strip()
    org_slug = (
        getattr(args, "org", None)
        or os.environ.get("DEVSPER_PLATFORM_ORG")
        or cs.get("platform", "org")
        or ""
    ).strip()
    token = (
        getattr(args, "token", None)
        or os.environ.get("DEVSPER_PLATFORM_TOKEN")
        or cs.get("platform", "token")
        or ""
    ).strip()
    if not api_url or not org_slug:
        print("Missing platform config. Provide --api-url and --org.", file=sys.stderr)
        return 1
    if not token:
        print(
            "Missing platform token. Provide --token or set DEVSPER_PLATFORM_TOKEN.",
            file=sys.stderr,
        )
        return 1

    _track_conversion_event(
        "platform_connect_started", {"api_url": api_url, "org": org_slug}
    )
    api = PlatformAPIRequestBuilder(base_url=api_url, org_slug=org_slug, token=token)
    try:
        _ = api.get_json("/health")
        _ = api.get_json(f"/orgs/{org_slug}/runs", params={"limit": 1, "offset": 0})
    except Exception as e:
        print(f"Platform connect verification failed: {e}", file=sys.stderr)
        _track_conversion_event("platform_connect_failed", {"reason": str(e)})
        return 1

    cs.set("platform", "api_url", api_url)
    cs.set("platform", "org", org_slug)
    cs.set("platform", "token", token)
    os.environ["DEVSPER_PLATFORM_API_URL"] = api_url
    os.environ["DEVSPER_PLATFORM_ORG"] = org_slug
    os.environ["DEVSPER_PLATFORM_TOKEN"] = token

    if not getattr(args, "skip_toml", False):
        try:
            _upsert_project_platform_memory_config(api_url, org_slug)
        except Exception:
            pass

    print(f"Connected platform: api={api_url} org={org_slug}")
    print(
        "Use `devsper cloud run` to route runs to platform."
    )
    _track_conversion_event("platform_connect_succeeded", {"org": org_slug})
    return 0


def _run_platform_roi() -> int:
    p = _conversion_events_path()
    if not p.exists():
        print("No conversion telemetry yet.")
        return 0
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    counts: dict[str, int] = {}
    for r in rows:
        e = str(r.get("event", ""))
        counts[e] = counts.get(e, 0) + 1
    print("Conversion ROI dashboard (local)")
    for k in sorted(counts.keys()):
        print(f"- {k}: {counts[k]}")
    return 0


def _run_swarm(args: object) -> int:
    """Run swarm. Uses live view unless --quiet, --plain, or non-TTY."""
    _track_conversion_event("runtime_user_detected", {"command": "run"})
    if getattr(args, "shadow", False):
        return _run_shadow_mode(args)
    print("Running locally...")
    # Local profile fast-path: route through platform pool + local workers.
    if os.environ.get("DEVSPER_PROFILE", "").strip().lower() == "local":
        try:
            return _run_swarm_via_local_pool(args)
        except Exception as e:
            print(
                f"Local pool failed, falling back to in-process swarm: {e}",
                file=sys.stderr,
            )
    from devsper.config import get_config
    from devsper.utils.event_logger import EventLog
    from devsper.swarm.swarm import Swarm
    from devsper.runtime.executor import Executor
    from devsper.runtime.agent_runner import AgentRunner
    from devsper.memory.memory_router import MemoryRouter
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex

    _ = (Executor, AgentRunner)

    task = getattr(args, "task", "Summarize swarm intelligence in one paragraph.")
    quiet = getattr(args, "quiet", False)
    summary_only = getattr(args, "summary", False)
    json_output = getattr(args, "json_output", False)
    plain = getattr(args, "plain", False) or not sys.stdout.isatty()
    reporter = getattr(args, "reporter", False)
    use_live_view = not quiet and not plain and not reporter and sys.stdout.isatty()

    cfg = get_config()
    from devsper.platform.redis_results_sink import build_reporter_sinks_chain

    _prid = (os.environ.get("DEVSPER_PLATFORM_RUN_ID") or "").strip()
    _chain = build_reporter_sinks_chain(cfg.events_dir)
    event_log = EventLog(
        events_folder_path=cfg.events_dir,
        run_id=_prid if _prid else None,
        platform_sink=_chain,
    )
    log_path = getattr(event_log, "log_path", None)
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(
            get_default_store(),
            ranking_backend=getattr(cfg.memory, "backend", "local"),
        ),
        top_k=5,
    )
    workers = getattr(cfg.swarm, "workers", 2)
    clarification_queue = None
    if use_live_view or reporter:
        import queue

        clarification_queue = queue.Queue()
    swarm = Swarm(
        worker_count=workers,
        worker_model=cfg.worker_model,
        planner_model=cfg.planner_model,
        event_log=event_log,
        memory_router=memory_router,
        use_tools=True,
        clarification_queue=clarification_queue,
    )
    results_holder: list[dict] = []
    run_id = getattr(event_log, "run_id", "") or ""

    # Headless HITL bridge: publish clarification_requested and wait for answers.
    stop_event = None
    bridge_thread = None
    bridge_event_sink = None
    if reporter and run_id:
        try:
            import redis

            redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
            r = redis.Redis.from_url(redis_url, decode_responses=True)

            from devsper.platform.reporter import hitl_bridge_thread

            stop_event = threading.Event()
            # `event_log` uses `platform_sink=_chain` when reporter is enabled.
            bridge_event_sink = _chain
            bridge_thread = threading.Thread(
                target=hitl_bridge_thread,
                args=(r, run_id, clarification_queue, swarm, stop_event, bridge_event_sink),
                daemon=True,
            )
            bridge_thread.start()
        except Exception:
            from devsper.cli.ui import console

            console.print(
                "[yellow]Reporter HITL bridge could not start; run may not pause for user input.[/yellow]"
            )

    hitl_resolver = None
    if (
        getattr(getattr(cfg, "hitl", None), "enabled", False)
        and sys.stdout.isatty()
        and not plain
    ):
        from devsper.hitl.approval import ApprovalStore

        _store = ApprovalStore(getattr(cfg, "data_dir", ".devsper"))

        def _prompt_resolver(approval, policy):  # sync, runs in thread
            try:
                from devsper.cli.ui import console

                task_desc = (getattr(approval.task, "description", "") or "")[:60]
                console.print()
                console.print("[hive.warning]Approval required[/]")
                console.print(f"  Task: {task_desc}...")
                console.print(f"  Trigger: {getattr(approval.trigger, 'type', '?')}")
                preview = (approval.proposed_result or "")[:200]
                if preview:
                    console.print(f"  Result preview: {preview}...")
                from rich.prompt import Prompt

                choice = Prompt.ask(
                    "Approve this result? [y/n]", choices=["y", "n"], default="y"
                )
                approved = choice.lower() == "y"
                _store.resolve(approval.request_id, approved, "")
                return approved
            except Exception:
                return False

        hitl_resolver = _prompt_resolver

    def _run() -> None:
        results_holder.append(swarm.run(task, hitl_resolver=hitl_resolver))

    thread = threading.Thread(target=_run, daemon=False)
    thread.start()

    if use_live_view:
        try:
            from devsper.cli.ui import run_live_view, print_run_summary

            state = run_live_view(
                log_path=log_path,
                run_id=run_id,
                worker_count=workers,
                stop_check=lambda: not thread.is_alive(),
                clarification_queue=clarification_queue,
                swarm=swarm,
            )
            thread.join()
            results = results_holder[0] if results_holder else {}
            if json_output:
                import json

                out = {
                    "run_id": state.run_id_short,
                    "tasks": len(state.tasks),
                    "results": results,
                }
                print(json.dumps(out))
            else:
                print_run_summary(state, results, summary_only=summary_only)
        except Exception:
            thread.join()
            results = results_holder[0] if results_holder else {}
            from devsper.cli.ui import console

            for task_id, result in results.items():
                console.print(f"--- {task_id} ---")
                console.print((result or "")[:2000])
                if (result or "") and len(result) > 2000:
                    console.print("...")
    else:
        if not quiet:
            from devsper.cli.run_progress import read_run_status

            last_status = ""
            while thread.is_alive():
                status, running = read_run_status(log_path, worker_count=workers)
                line = status
                if len(running) > 1:
                    line += f"  (parallel: {len(running)} tasks)"
                if line != last_status:
                    sys.stderr.write("\r  " + line.ljust(70))
                    sys.stderr.flush()
                    last_status = line
                time.sleep(0.3)
            sys.stderr.write("\n")
            sys.stderr.flush()
        thread.join()
        if stop_event is not None:
            stop_event.set()
        if bridge_thread is not None:
            bridge_thread.join(timeout=1.0)
        results = results_holder[0] if results_holder else {}
        if json_output:
            import json

            print(json.dumps(results))
        else:
            from devsper.cli.ui import console

            for task_id, result in results.items():
                console.print(f"--- {task_id} ---")
                console.print((result or "")[:2000])
                if (result or "") and len(result) > 2000:
                    console.print("...")
    try:
        if getattr(cfg, "export", None) and getattr(cfg.export, "auto_export_on_run", False):
            from devsper.export.service import ExportOptions, export_all_runs

            ts = int(time.time())
            out_dir = f".devsper/exports/runs_{ts}"
            fmt = str(getattr(cfg.export, "format", "docx") or "docx").lower()
            if fmt == "pdf":
                pdf_pipeline = "both"
            else:
                # docx/html/all still benefit from HTML PDF where available.
                pdf_pipeline = "html"
            manifest = export_all_runs(
                ExportOptions(
                    output_dir=out_dir,
                    limit=int(getattr(cfg.export, "limit", 1) or 1),
                    pdf_pipeline=pdf_pipeline,
                )
            )
            files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
            print(f"Auto-export complete: {out_dir}")
            if fmt in {"docx", "all"} and files.get("all_runs_docx"):
                print(f"DOCX: {files.get('all_runs_docx')}")
            if fmt in {"html", "all"} and files.get("all_runs_html"):
                print(f"HTML: {files.get('all_runs_html')}")
            if fmt in {"pdf", "all"}:
                pdf_out = (manifest.get("pdf_outputs", {}) or {}).get("html_pdf")
                if pdf_out:
                    print(f"PDF: {pdf_out}")
    except Exception as e:
        print(f"Auto-export failed: {e}", file=sys.stderr)
    return 0


def _run_swarm_via_local_pool(args: object) -> int:
    import asyncio
    import uuid
    import json as _json

    task_text = getattr(args, "task", "") or ""
    run_id = str(uuid.uuid4())
    org_id = os.environ.get("DEVSPER_ORG_ID", "local-org")
    user_id = os.environ.get("DEVSPER_USER_ID", "local-user")
    redis_url = _resolve_pool_redis_url(profile="local")

    pool_cfg = _import_pool_submodule("config").load_pool_config("local")

    crypto_mod = _import_pool_submodule("crypto")
    manager_mod = _import_pool_submodule("manager")
    models_mod = _import_pool_submodule("models")
    store_mod = _import_pool_submodule("store")
    encrypt_payload = crypto_mod.encrypt_payload
    generate_org_keypair = crypto_mod.generate_org_keypair
    PoolManager = manager_mod.PoolManager
    QueuedTask = models_mod.QueuedTask
    RedisPoolStore = store_mod.RedisPoolStore
    from devsper.credentials.store import CredentialStore

    # Ensure org key exists in keyring (local convenience).
    cs = CredentialStore()
    priv_hex = cs.get("org", "private_key")
    if not priv_hex:
        priv, pub = generate_org_keypair()
        cs.set("org", "private_key", priv.hex())
        pub_hex = pub.hex()
    else:
        # derive public key from private
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        priv = bytes.fromhex(priv_hex)
        pub_hex = (
            X25519PrivateKey.from_private_bytes(priv)
            .public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            .hex()
        )

    org_pub = bytes.fromhex(pub_hex)

    payload = {
        "task_id": run_id,
        "prompt": task_text,
        "context": "",
        "tools": [],
        "model": os.environ.get("DEVSPER_WORKER_MODEL", "mock"),
        "system_prompt": "",
    }
    payload_enc = encrypt_payload(_json.dumps(payload).encode(), org_pub)

    class _Bus:
        def __init__(self, url: str):
            import redis

            self._r = redis.Redis.from_url(url, decode_responses=True)

        def publish(self, channel: str, payload: dict):
            self._r.publish(channel, _json.dumps(payload))

    async def _run_once() -> int:
        store = RedisPoolStore(redis_url)
        bus = _Bus(redis_url)
        pool = PoolManager(store=store, bus=bus, config=pool_cfg)
        qt = QueuedTask(
            task_id=run_id,
            org_id=org_id,
            user_id=user_id,
            priority=1,
            payload_enc=payload_enc,
        )
        await pool.enqueue(qt)

        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(f"devsper:task:{run_id}:result")
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            if not data:
                continue
            res = _json.loads(data)
            if res.get("success"):
                print(res.get("result", ""))
                return 0
            print(res.get("error", "error"), file=sys.stderr)
            return 1

    return asyncio.run(_run_once())


def _run_meta(
    mega_task: str, max_swarms: int | None = None, budget: float | None = None
) -> int:
    """Run meta-planner: decompose mega-task into sub-swarms, run them, print synthesis."""
    import asyncio
    from devsper.orchestration import MetaPlanner
    from devsper.config import get_config

    cfg = get_config()
    planner_model = getattr(cfg.models, "planner", "mock")
    planner = MetaPlanner(model_name=planner_model)
    result = asyncio.run(
        planner.run(mega_task, max_swarms=max_swarms, budget_usd=budget)
    )
    from devsper.cli.ui import console

    console.print(result.final_synthesis)
    if result.sla_breaches:
        console.print(
            "\n[hive.warning]SLA breaches:[/]",
            [f"{b.swarm_id}: {b.breach_type}" for b in result.sla_breaches],
        )
    return 0


def _run_meta_plan(mega_task: str) -> int:
    """Decompose only: print SubSwarmSpecs as table, no execution."""
    import asyncio
    from devsper.orchestration import MetaPlanner
    from devsper.config import get_config

    cfg = get_config()
    planner_model = getattr(cfg.models, "planner", "mock")
    planner = MetaPlanner(model_name=planner_model)
    specs = asyncio.run(planner.decompose(mega_task))
    try:
        from rich.console import Console
        from rich.table import Table

        c = Console()
        t = Table(title="SubSwarmSpecs")
        t.add_column("swarm_id", style="cyan")
        t.add_column("root_task", style="green", max_width=50)
        t.add_column("priority")
        t.add_column("workers")
        t.add_column("depends_on")
        for s in specs:
            t.add_row(
                s.swarm_id,
                (s.root_task or "")[:50],
                str(s.priority),
                str(s.worker_count),
                ",".join(s.depends_on) or "-",
            )
        c.print(t)
    except ImportError:
        from devsper.cli.ui import console

        for s in specs:
            console.print(
                f"  {s.swarm_id}: priority={s.priority} workers={s.worker_count} deps={s.depends_on}"
            )
            console.print(f"    task: {(s.root_task or '')[:80]}")
    return 0


def _run_approvals_list() -> int:
    """Table: request_id, task (truncated), trigger, created, expires, status."""
    from devsper.config import get_config
    from devsper.hitl.approval import ApprovalStore

    cfg = get_config()
    store = ApprovalStore(cfg.data_dir)
    pending = store.list_pending()
    try:
        from rich.console import Console
        from rich.table import Table

        c = Console()
        t = Table(title="Pending approvals")
        t.add_column("request_id", style="cyan")
        t.add_column("task", style="green", max_width=40)
        t.add_column("trigger", style="yellow")
        t.add_column("created")
        t.add_column("expires")
        t.add_column("status")
        for r in pending:
            desc = (getattr(r.task, "description", "") or "")[:40]
            t.add_row(
                r.request_id[:12],
                desc,
                str(r.trigger.type),
                r.created_at[:19],
                r.expires_at[:19],
                r.status,
            )
        c.print(t)
    except ImportError:
        from devsper.cli.ui import console

        for r in pending:
            console.print(
                f"  {r.request_id}  {getattr(r.task, 'description', '')[:50]}  {r.trigger.type}  {r.status}"
            )
    return 0


def _run_approvals_show(request_id: str) -> int:
    """Full approval request details."""
    from devsper.config import get_config
    from devsper.hitl.approval import ApprovalStore

    cfg = get_config()
    store = ApprovalStore(cfg.data_dir)
    req = store.get(request_id)
    if req is None:
        from devsper.cli.ui import err_console

        err_console.print(f"No approval request found: {request_id}")
        return 1
    from devsper.cli.ui import console

    console.print("Request ID:", req.request_id)
    console.print("Task:", getattr(req.task, "description", ""))
    console.print("Proposed result:", (req.proposed_result or "")[:500])
    console.print("Trigger:", req.trigger.type, req.trigger.threshold)
    console.print("Created:", req.created_at, "Expires:", req.expires_at)
    console.print("Status:", req.status)
    if req.reviewer_notes:
        console.print("Notes:", req.reviewer_notes)
    return 0


def _run_approvals_approve(request_id: str, notes: str = "") -> int:
    from devsper.config import get_config
    from devsper.hitl.approval import ApprovalStore

    cfg = get_config()
    store = ApprovalStore(cfg.data_dir)
    store.resolve(request_id, approved=True, notes=notes)
    from devsper.cli.ui import console

    console.print(f"[hive.success]Approved[/] {request_id}")
    return 0


def _run_approvals_reject(request_id: str, notes: str = "") -> int:
    from devsper.config import get_config
    from devsper.hitl.approval import ApprovalStore

    cfg = get_config()
    store = ApprovalStore(cfg.data_dir)
    store.resolve(request_id, approved=False, notes=notes)
    from devsper.cli.ui import console

    console.print(f"[hive.error]Rejected[/] {request_id}")
    return 0


def _run_approvals_watch() -> int:
    """Live-updating table of pending approvals, refresh every 10s."""
    import time
    from devsper.config import get_config
    from devsper.hitl.approval import ApprovalStore

    cfg = get_config()
    store = ApprovalStore(cfg.data_dir)
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.live import Live

        c = Console()

        def make_table():
            pending = store.list_pending()
            t = Table(title="Pending approvals (refresh 10s)")
            t.add_column("request_id")
            t.add_column("task", max_width=50)
            t.add_column("trigger")
            t.add_column("status")
            for r in pending:
                t.add_row(
                    r.request_id[:14],
                    (getattr(r.task, "description", "") or "")[:50],
                    str(r.trigger.type),
                    r.status,
                )
            return t

        with Live(make_table(), refresh_per_second=0.1, console=c) as live:
            while True:
                time.sleep(10)
                live.update(make_table())
    except ImportError:
        while True:
            pending = store.list_pending()
            for r in pending:
                print(r.request_id, getattr(r.task, "description", "")[:40], r.status)
            time.sleep(10)
    return 0


def _run_tui() -> int:
    """Launch the TUI."""
    from devsper.config import get_config
    from devsper.tui.app import run_tui

    cfg = get_config()
    run_tui(events_folder=cfg.events_dir)
    return 0


def _run_repl(args=None) -> int:
    """Launch the interactive coding REPL (default when no subcommand given)."""
    from pathlib import Path

    from devsper.workspace.context import WorkspaceContext
    from devsper.workspace.session import SessionHistory
    from devsper.workspace.repl import CodeREPL

    workspace = WorkspaceContext.discover(Path.cwd())
    workspace.storage_dir.mkdir(parents=True, exist_ok=True)

    session = SessionHistory(workspace.storage_dir)

    new_session = getattr(args, "new", False) if args is not None else False
    session_id = getattr(args, "session", None) if args is not None else None

    if session_id:
        try:
            session.load_session(session_id)
            new_session = False
        except FileNotFoundError:
            print(f"Session '{session_id}' not found.")
            return 1

    repl = CodeREPL(workspace, session, new_session=new_session)
    repl.start()
    return 0


def _run_research(path: str) -> int:
    """Run literature review example on a directory."""
    root = _project_root()
    script = root / "examples" / "research" / "literature_review.py"
    if not script.exists():
        print(
            "Error: examples/research/literature_review.py not found", file=sys.stderr
        )
        return 1
    return _run_example(script, path or ".")


def _run_analyze(path: str) -> int:
    """Run repository analysis example."""
    root = _project_root()
    script = root / "examples" / "coding" / "analyze_repository.py"
    if not script.exists():
        print("Error: examples/coding/analyze_repository.py not found", file=sys.stderr)
        return 1
    return _run_example(script, path or ".")


def _run_analyze_dispatch(args: object) -> int:
    """Dispatch: run_id -> run analysis; path (., /path) -> repo analysis."""
    run_id_or_path = getattr(args, "run_id_or_path", None)
    no_ai = getattr(args, "no_ai", False)
    json_out = getattr(args, "analyze_json", False)
    if run_id_or_path is None or (
        isinstance(run_id_or_path, str) and not run_id_or_path.strip()
    ):
        from rich.console import Console
        from devsper.runtime.run_history import RunHistory

        console = Console()
        rows = RunHistory().list_runs(limit=5)
        if rows:
            console.print(
                "Recent runs (use [cyan]devsper analyze <run_id>[/] for run analysis):"
            )
            for r in rows[:5]:
                console.print(f"  [dim]{r.run_id}[/]")
        else:
            console.print(
                "No runs yet. Use [cyan]devsper analyze <run_id>[/] after a run, or [cyan]devsper analyze .[/] for repo analysis."
            )
        return 0
    s = str(run_id_or_path).strip()
    if s in (".", "..") or "/" in s or os.path.exists(s):
        return _run_analyze(s)
    return _run_analyze_run(s, no_ai=no_ai, json_output=json_out)


def _run_analyze_run(
    run_id: str,
    no_ai: bool = False,
    json_output: bool = False,
) -> int:
    """Analyze a swarm run: load events, build report, optional LLM analysis."""
    from devsper.config import get_config
    from devsper.intelligence.analysis import (
        build_report_from_events,
        analyze,
        print_run_report,
        RunReport,
    )
    from devsper.intelligence.analysis.cost_estimator import CostEstimator
    from rich.console import Console
    from rich.panel import Panel

    cfg = get_config()
    events_dir = cfg.events_dir
    console = Console()

    try:
        report = build_report_from_events(run_id, events_dir)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/] {e}")
        return 1
    except ValueError as e:
        console.print(f"[red]Error:[/] {e}")
        return 1

    if json_output:
        import json
        from dataclasses import asdict
        from devsper.intelligence.analysis.run_report import TaskSummary

        def _serialize(obj):
            if hasattr(obj, "value"):
                return obj.value
            if hasattr(obj, "__dataclass_fields__"):
                return {
                    k: _serialize(getattr(obj, k)) for k in obj.__dataclass_fields__
                }
            return obj

        out = {
            "run_id": report.run_id,
            "root_task": report.root_task,
            "strategy": report.strategy,
            "started_at": report.started_at,
            "finished_at": report.finished_at,
            "total_duration_seconds": report.total_duration_seconds,
            "total_tasks": report.total_tasks,
            "completed_tasks": report.completed_tasks,
            "failed_tasks": report.failed_tasks,
            "skipped_tasks": report.skipped_tasks,
            "critical_path": report.critical_path,
            "bottleneck_task_id": report.bottleneck_task_id,
            "tools_called": report.tools_called,
            "tool_success_rate": report.tool_success_rate,
            "estimated_cost_usd": report.estimated_cost_usd,
            "models_used": report.models_used,
            "peak_parallelism": report.peak_parallelism,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "description": t.description,
                    "role": t.role,
                    "status": _serialize(t.status),
                    "duration_seconds": t.duration_seconds,
                    "tools_used": t.tools_used,
                    "tool_failures": t.tool_failures,
                    "tokens_used": t.tokens_used,
                    "retry_count": t.retry_count,
                    "error": t.error,
                }
                for t in report.tasks
            ],
        }
        console.print(json.dumps(out, indent=2))
        return 0

    print_run_report(report, console)
    if not no_ai:
        worker_model = getattr(cfg, "worker_model", None) or getattr(
            cfg.models, "worker", "gpt-4o-mini"
        )
        from devsper.utils.models import resolve_model

        worker_model = resolve_model(worker_model, "analysis")
        analysis_text = analyze(
            report,
            worker_model,
            stream_callback=lambda c: console.print(c, end=""),
        )
        report.plain_english_analysis = analysis_text
        console.print()
        console.print(
            Panel(analysis_text, title="Plain-English Analysis", border_style="dim")
        )
    return 0


def _run_runs(args: object) -> int:
    """List run history (Rich table) or run-analyze <run_id> --no-ai when run_id given."""
    run_id = getattr(args, "run_id", None)
    if run_id and str(run_id).strip():
        return _run_analyze_run(str(run_id).strip(), no_ai=True, json_output=False)
    from devsper.runtime.run_history import RunHistory

    limit = getattr(args, "limit", 20)
    failed = getattr(args, "failed", False)
    json_out = getattr(args, "runs_json", False)
    history = RunHistory()
    filter_status = "failed" if failed else None
    rows = history.list_runs(limit=limit, filter_status=filter_status)
    if json_out:
        import json

        out = [
            {
                "run_id": r.run_id,
                "root_task": r.root_task[:200],
                "strategy": r.strategy,
                "started_at": r.started_at,
                "duration_seconds": r.duration_seconds,
                "total_tasks": r.total_tasks,
                "completed_tasks": r.completed_tasks,
                "failed_tasks": r.failed_tasks,
                "estimated_cost_usd": r.estimated_cost_usd,
            }
            for r in rows
        ]
        print(json.dumps(out, indent=2))
        return 0
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Run history")
    table.add_column("Run ID", style="dim", max_width=36, overflow="fold")
    table.add_column("Task", max_width=40, overflow="fold")
    table.add_column("Strategy", width=10)
    table.add_column("Status", width=14)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Tasks", justify="right", width=6)
    table.add_column("Cost", justify="right", width=10)
    table.add_column("Date", style="dim", width=24)
    for r in rows:
        short_id = r.run_id[:32] + "…" if len(r.run_id) > 32 else r.run_id
        task_preview = (r.root_task or "")[:40] + (
            "…" if len(r.root_task or "") > 40 else ""
        )
        if r.failed_tasks > 0 and r.completed_tasks > 0:
            status = "[yellow]⚠ partial[/]"
        elif r.failed_tasks > 0:
            status = "[red]✗ failed[/]"
        else:
            status = "[green]✓ completed[/]"
        dur = f"{r.duration_seconds:.1f}s"
        tasks = f"{r.completed_tasks}/{r.total_tasks}"
        cost = (
            f"${r.estimated_cost_usd:.4f}" if r.estimated_cost_usd is not None else "—"
        )
        date = (r.started_at or "")[:24]
        table.add_row(
            short_id, task_preview, r.strategy or "—", status, dur, tasks, cost, date
        )
    if rows:
        console.print(table)
    else:
        console.print(
            'No runs recorded. Run a swarm first (e.g. [cyan]devsper run "task"[/]).'
        )
    return 0


def _run_export_runs(args: object) -> int:
    """Export run history into multiple formats + PDF pipelines."""
    from rich.console import Console
    from devsper.export.service import ExportOptions, export_all_runs

    out_dir = getattr(args, "output", "") or ""
    if not out_dir:
        ts = int(time.time())
        out_dir = f".devsper/exports/runs_{ts}"
    limit = getattr(args, "limit", None)
    pdf_pipeline = getattr(args, "pdf_pipeline", "both") or "both"
    console = Console()
    manifest = export_all_runs(
        ExportOptions(
            output_dir=out_dir,
            limit=limit,
            pdf_pipeline=pdf_pipeline,
        )
    )
    console.print(f"[green]Export complete[/]  runs={manifest.get('run_count', 0)}")
    console.print(f"Output: [cyan]{manifest.get('output_dir', out_dir)}[/]")
    files = manifest.get("files", {}) or {}
    for k in (
        "all_runs_md",
        "all_runs_rst",
        "all_runs_tex",
        "all_runs_bib",
        "all_runs_html",
        "all_runs_docx",
    ):
        if k in files:
            console.print(f"  - {k}: {files[k]}")
    pdf_out = manifest.get("pdf_outputs", {}) or {}
    pdf_err = manifest.get("pdf_errors", {}) or {}
    for k, v in pdf_out.items():
        console.print(f"  - {k}: {v}")
    for k, v in pdf_err.items():
        console.print(f"[yellow]  - {k} unavailable:[/] {v}")
    return 0


def _workflow_dispatch(args: object) -> int:
    """Dispatch workflow list | validate | run | <name>."""
    a = args
    first = getattr(a, "first", None)
    second = getattr(a, "second", None)
    inputs = getattr(a, "input", None) or []
    if first == "list":
        return _workflow_list()
    if first == "validate":
        return _workflow_validate(second or "")
    if first == "run":
        return _workflow_run(second or "", inputs)
    if first:
        return _workflow_run(first, inputs)
    return _workflow_list()


def _workflow_list() -> int:
    """List all defined workflows with name, version, step count, description."""
    try:
        from rich.console import Console
        from rich.table import Table
        from devsper.workflow.loader import list_workflows, load_workflow
    except ImportError:
        from devsper.workflow.loader import list_workflows, load_workflow

        names = list_workflows()
        for n in names:
            wf = load_workflow(n)
            if wf:
                print(
                    f"{wf.name}  v{wf.version}  steps={len(wf.steps)}  {wf.description or ''}"
                )
        return 0
    console = Console()
    names = list_workflows()
    if not names:
        console.print(
            "No workflows defined. Add [workflow] to workflow.devsper.toml or devsper.toml."
        )
        return 0
    table = Table(title="Workflows")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Steps", justify="right")
    table.add_column("Description", style="dim")
    for n in names:
        wf = load_workflow(n)
        if wf:
            table.add_row(
                wf.name,
                wf.version,
                str(len(wf.steps)),
                (wf.description or "")[:60],
            )
    console.print(table)
    return 0


def _workflow_validate(name: str) -> int:
    """Validate workflow by name. Exit 0 if valid, 1 if errors."""
    from devsper.workflow.loader import load_workflow
    from devsper.workflow.validator import ValidationReport, validate_workflow

    wf = load_workflow(name)
    if not wf:
        print(f"Workflow '{name}' not found.", file=sys.stderr)
        return 1
    report = validate_workflow(wf)
    try:
        from rich.console import Console
        from rich.markup import escape

        console = Console()
        if report.errors:
            for e in report.errors:
                console.print(f"[red]✗[/red] {escape(e)}")
        if report.warnings:
            for w in report.warnings:
                console.print(f"[yellow]⚠[/yellow] {escape(w)}")
        if report.info:
            for i in report.info:
                console.print(f"[dim]ℹ[/dim] {escape(i)}")
        if report.valid and not report.errors:
            console.print("[green]✓[/green] Validation passed.")
        elif report.errors:
            console.print("[red]✗[/red] Validation failed.")
    except ImportError:
        for e in report.errors:
            print(f"✗ {e}", file=sys.stderr)
        for w in report.warnings:
            print(f"⚠ {w}", file=sys.stderr)
        for i in report.info:
            print(f"ℹ {i}")
        if report.valid:
            print("✓ Validation passed.")
        else:
            print("✗ Validation failed.", file=sys.stderr)
    return 0 if report.valid else 1


def _workflow_run(name: str, input_pairs: list[str]) -> int:
    """Run workflow by name with optional --input key=value. Print summary table after."""
    from devsper.config import get_config
    from devsper.memory.memory_router import MemoryRouter
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex
    from devsper.workflow.loader import load_workflow
    from devsper.workflow.runner import WorkflowRunner

    wf = load_workflow(name)
    if not wf:
        print(f"Workflow '{name}' not found.", file=sys.stderr)
        return 1
    inputs = {}
    for pair in input_pairs:
        if "=" in pair:
            k, v = pair.split("=", 1)
            inputs[k.strip()] = v.strip()
        else:
            inputs[pair.strip()] = ""
    cfg = get_config()
    memory_router = MemoryRouter(
        store=get_default_store(),
        index=MemoryIndex(
            get_default_store(),
            ranking_backend=getattr(cfg.memory, "backend", "local"),
        ),
        top_k=5,
    )
    runner = WorkflowRunner()
    try:
        ctx = runner.run(
            wf,
            inputs=inputs,
            worker_model=cfg.worker_model,
            worker_count=getattr(cfg.swarm, "workers", 2),
            memory_router=memory_router,
            use_tools=True,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Workflow run summary")
        table.add_column("Step", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Note", style="dim")
        for step_id, sr in ctx.steps.items():
            if sr.skipped:
                status = "[yellow]skipped[/yellow]"
            elif sr.error:
                status = "[red]failed[/red]"
            else:
                status = "[green]completed[/green]"
            table.add_row(
                step_id,
                status,
                f"{sr.duration_seconds:.2f}s",
                sr.error or ("(skipped)" if sr.skipped else ""),
            )
        console.print(table)
    except ImportError:
        for step_id, sr in ctx.steps.items():
            status = (
                "skipped" if sr.skipped else ("failed" if sr.error else "completed")
            )
            print(
                f"  {step_id}  {status}  {sr.duration_seconds:.2f}s  {sr.error or ''}"
            )
    for step_id, sr in ctx.steps.items():
        if not sr.skipped and not sr.error and sr.raw_result:
            print(f"\n--- {step_id} ---")
            print((sr.raw_result or "")[:2000])
            if (sr.raw_result or "") and len(sr.raw_result) > 2000:
                print("...")
    return 0


def _run_query(query_str: str) -> int:
    """Query the knowledge graph: entity search and relationship traversal."""
    from devsper.knowledge.knowledge_graph import KnowledgeGraph
    from devsper.knowledge.query import query as kg_query
    from devsper.memory.memory_store import get_default_store

    store = get_default_store()
    kg = KnowledgeGraph(store=store)
    kg.build_from_memory()
    result = kg_query(kg, query_str or "")
    if not result.entities and not result.edges and not result.documents:
        print("No matching entities or documents.")
        return 0
    if result.entities:
        print("Entities:")
        for node_id, label in result.entities[:30]:
            print(f"  {node_id}  {label[:80]}")
    if result.edges:
        print("\nRelationships:")
        for a, b, et in result.edges[:30]:
            print(f"  {a} --[{et}]--> {b}")
    if result.documents:
        print("\nDocuments mentioning query:")
        for doc_id in result.documents[:20]:
            print(f"  {doc_id}")
    return 0


def _run_init(no_interactive: bool = False) -> int:
    """Run init: wizard with welcome screen (interactive) or minimal config (--no-interactive)."""
    try:
        from devsper.cli.ui.onboarding import run_init_wizard

        return run_init_wizard(no_interactive=no_interactive)
    except ImportError:
        from devsper.cli.init import run_init

        return run_init(interactive=not no_interactive)


def _run_init_md() -> int:
    """Generate devsper.md project instructions via LLM."""
    from pathlib import Path

    from devsper.cli.init import run_init_md

    return run_init_md(Path.cwd())


def _run_credentials(args: object) -> int:
    """Run credentials subcommand: set, list, delete, migrate."""
    from devsper.credentials.cli import run_credentials

    return run_credentials(args)


def _run_doctor() -> int:
    """Run doctor subcommand: verify GITHUB_TOKEN, OpenAI, config, tools."""
    from devsper.cli.init import run_doctor

    return run_doctor()


def _run_mcp_list() -> int:
    """List configured MCP servers and their tool counts (from live discovery)."""
    from devsper.config import get_config
    from devsper.tools.mcp import discover_mcp_tools

    cfg = get_config()
    servers = getattr(getattr(cfg, "mcp", None), "servers", None) or []
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="MCP servers")
        table.add_column("Name", style="cyan")
        table.add_column("Transport", style="dim")
        table.add_column("Tools", justify="right")
        for s in servers:
            sname = getattr(s, "name", "?")
            try:
                adapters = discover_mcp_tools(s)
                count = len(adapters)
            except Exception:
                count = "—"
            table.add_row(sname, getattr(s, "transport", "?"), str(count))
        if not servers:
            console.print(
                "No MCP servers configured. Add [[mcp.servers]] to devsper.toml or use [cyan]devsper mcp add[/]."
            )
        else:
            console.print(table)
    except ImportError:
        for s in servers:
            print(getattr(s, "name", "?"), getattr(s, "transport", "?"))
    return 0


def _run_mcp_test(server_name: str) -> int:
    """Connect to server, list tools, print names and descriptions. Exit 1 if connection fails."""
    from devsper.config import get_config

    cfg = get_config()
    servers = getattr(getattr(cfg, "mcp", None), "servers", None) or []
    server = next((s for s in servers if getattr(s, "name", "") == server_name), None)
    if not server:
        print(
            f"Error: MCP server '{server_name}' not found in config.", file=sys.stderr
        )
        return 1
    try:
        from devsper.tools.mcp import discover_mcp_tools

        adapters = discover_mcp_tools(server)
        print(f"Connected to '{server_name}'. Tools: {len(adapters)}")
        for a in adapters:
            print(
                f"  - {getattr(a, '_mcp_tool_name', a.name)}: {(a.description or '')[:80]}"
            )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_mcp_add() -> int:
    """Interactive: prompt for transport, command/url, name; append to devsper.toml [mcp.servers]."""
    from pathlib import Path
    from devsper.config.config_loader import project_config_paths

    config_path = None
    for p in project_config_paths():
        if p.is_file():
            config_path = p
            break
    if not config_path:
        print(
            "Error: No devsper.toml found. Run [cyan]devsper init[/] first.",
            file=sys.stderr,
        )
        return 1
    try:
        name = input("Server name (e.g. filesystem): ").strip() or "mcp-server"
        transport = (
            input("Transport (stdio|http|sse) [stdio]: ").strip().lower() or "stdio"
        )
        if transport == "stdio":
            cmd_str = input(
                "Command (space-separated, e.g. npx -y @modelcontextprotocol/server-filesystem /tmp): "
            ).strip()
            command = cmd_str.split() if cmd_str else []
            url = None
        else:
            command = None
            url = input("URL (e.g. http://localhost:3000): ").strip() or None
        toml = config_path.read_text()
        # Append [[mcp.servers]] entry
        entry = f'\n[[mcp.servers]]\nname = "{name}"\ntransport = "{transport}"\n'
        if command:
            entry += f"command = {json.dumps(command)}\n"
        if url:
            entry += f'url = "{url}"\n'
        if "\n[mcp]" not in toml and "[[mcp.servers]]" not in toml:
            toml = toml.rstrip() + "\n\n[mcp]\n" + entry.lstrip()
        else:
            toml = toml.rstrip() + "\n" + entry
        config_path.write_text(toml)
        print(f"Added MCP server '{name}' to {config_path}.")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_a2a_serve(port: int | None) -> int:
    """Start A2A server, print AgentCard URL."""
    from devsper.config import get_config
    from devsper.agents.a2a.server import run_a2a_server

    cfg = get_config()
    p = (
        port
        if port is not None
        else getattr(getattr(cfg, "a2a", None), "serve_port", 8080)
    )
    swarm_name = getattr(getattr(cfg, "swarm", None), "name", None) or "devsper"
    print(f"A2A server starting at http://localhost:{p}", file=sys.stderr)
    print(f"AgentCard: http://localhost:{p}/.well-known/agent.json", file=sys.stderr)
    run_a2a_server(host="0.0.0.0", port=p, swarm_name=swarm_name or "")
    return 0


def _run_a2a_discover(url: str) -> int:
    """Fetch AgentCard, print skills, optionally add to config."""
    try:
        from devsper.agents.a2a.client import A2AClient

        client = A2AClient()
        import asyncio

        card = asyncio.run(client.get_agent_card(url))
        print(f"Name: {card.name}")
        print(f"Description: {card.description}")
        print(f"Skills: {len(card.skills)}")
        for s in card.skills:
            desc = (s.description or "")[:60]
            if len(s.description or "") > 60:
                desc += "..."
            print(f"  - {s.id}: {s.name} — {desc}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_a2a_call(url: str, task: str) -> int:
    """Send task to external A2A agent, stream output."""
    try:
        from devsper.agents.a2a.client import A2AClient
        from devsper.agents.a2a.types import A2ATaskRequest
        import asyncio
        import uuid

        client = A2AClient()
        request = A2ATaskRequest(
            id=str(uuid.uuid4()), message={"text": task}, session_id=None
        )

        async def _stream():
            async for chunk in client.stream_task(url, request):
                print(chunk, end="", flush=True)

        asyncio.run(_stream())
        print()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_start(args) -> int:
    """Start a node in the foreground (controller, worker, or hybrid)."""
    try:
        role = getattr(args, "role", "hybrid")
        port = getattr(args, "port", None)
        workers = getattr(args, "workers", None)
        tags = getattr(args, "tags", "") or ""
        print(
            f"Node role: {role}, port: {port or 'config default'}, workers: {workers or 'config default'}",
            file=sys.stderr,
        )
        if tags:
            print(
                f"Tags: {[t.strip() for t in tags.split(',') if t.strip()]}",
                file=sys.stderr,
            )
        print(
            "Distributed node start: set nodes.mode=distributed and nodes.role in devsper.toml, then run your process.",
            file=sys.stderr,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_status(args) -> int:
    """Query controller GET /status."""
    url = getattr(args, "controller_url", None)
    if not url:
        try:
            from devsper.config import get_config

            url = get_config().nodes.controller_url
        except Exception:
            url = "http://localhost:7700"
    try:
        import httpx

        r = httpx.get(f"{url.rstrip('/')}/status", timeout=10.0)
        r.raise_for_status()
        data = r.json()
        from rich.console import Console
        from rich.table import Table

        cons = Console()
        cons.print(
            "[bold]Run[/bold]",
            data.get("run_id", ""),
            "[bold]Leader[/bold]",
            data.get("node_id", ""),
        )
        s = data.get("scheduler", {})
        cons.print(
            "Tasks:",
            s.get("completed", 0),
            "completed,",
            s.get("pending", 0),
            "pending",
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_workers(args) -> int:
    """List workers from controller GET /status."""
    url = getattr(args, "controller_url", None)
    if not url:
        try:
            from devsper.config import get_config

            url = get_config().nodes.controller_url
        except Exception:
            url = "http://localhost:7700"
    try:
        import httpx

        r = httpx.get(f"{url.rstrip('/')}/status", timeout=10.0)
        r.raise_for_status()
        data = r.json()
        for w in data.get("workers", []):
            print(w.get("node_id", "")[:8], w.get("host", ""), w.get("rpc_url", ""))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_drain(args) -> int:
    """POST /control drain target node."""
    url = getattr(args, "controller_url", None)
    try:
        from devsper.config import get_config

        url = url or get_config().nodes.controller_url
    except Exception:
        url = "http://localhost:7700"
    try:
        import httpx

        r = httpx.post(
            f"{url.rstrip('/')}/control",
            json={"command": "drain", "target": getattr(args, "node_id", "")},
            timeout=10.0,
        )
        r.raise_for_status()
        print("Drain sent.", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_node_logs(args) -> int:
    """Stream GET /stream/events."""
    url = getattr(args, "controller_url", None) or "http://localhost:7700"
    try:
        from devsper.config import get_config

        url = get_config().nodes.controller_url
    except Exception:
        pass
    print(
        "Connect to", url, "stream/events (--follow); not implemented", file=sys.stderr
    )
    return 0


def _run_pool_status(args) -> int:
    """Show pool worker counts by tier (Redis-backed best effort)."""
    redis_url = _resolve_pool_redis_url(getattr(args, "redis_url", None))
    try:
        import redis
    except Exception as e:
        print(
            "Pool commands require redis package. Install devsper[distributed].",
            file=sys.stderr,
        )
        return 1
    try:
        r = redis.Redis.from_url(redis_url, decode_responses=True)
        tiers = ["dedicated", "org", "global", "local"]
        out = {}
        for t in tiers:
            out[t] = int(r.scard(f"pool:tier:{t}:workers") or 0)
        print(json.dumps({"redis_url": redis_url, "tiers": out}))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_pool_workers(args) -> int:
    """List worker ids by tier (Redis-backed best effort)."""
    redis_url = _resolve_pool_redis_url(getattr(args, "redis_url", None))
    try:
        import redis
    except Exception:
        print(
            "Pool commands require redis package. Install devsper[distributed].",
            file=sys.stderr,
        )
        return 1
    try:
        r = redis.Redis.from_url(redis_url, decode_responses=True)
        tiers = ["dedicated", "org", "global", "local"]
        rows = []
        for t in tiers:
            for wid in sorted(r.smembers(f"pool:tier:{t}:workers") or []):
                raw = r.get(f"pool:worker:{wid}")
                rows.append({"tier": t, "worker_id": wid, "raw": raw})
        print(
            json.dumps({"workers": rows})
            if getattr(args, "json_output", False)
            else "\n".join([f"{w['tier']}\t{w['worker_id']}" for w in rows])
        )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_pool_queue(args) -> int:
    """Wait queue depth is process-local; report N/A for now."""
    print(
        json.dumps(
            {"queue_depth": None, "note": "wait queue is in pool-manager process"}
        )
    )
    return 0


def _run_pool_start(args) -> int:
    """Start local worker pool spawner (foreground)."""
    workers = getattr(args, "workers", 2)
    env = os.environ.copy()
    env["DEVSPER_PROFILE"] = "local"
    root = str(_project_root().parent.resolve())
    env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
    if not env.get("REDIS_URL"):
        env["REDIS_URL"] = _resolve_pool_redis_url(profile="local")
    cmd = [sys.executable, "-m", "devsper.pool.local_pool", "--workers", str(workers)]
    return subprocess.call(cmd, env=env)


def _run_org_keygen(args) -> int:
    """Generate org E2EE keypair and store private key in keyring."""
    try:
        crypto_mod = _import_pool_submodule("crypto")
        generate_org_keypair = crypto_mod.generate_org_keypair
        from devsper.credentials.store import CredentialStore
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    priv, pub = generate_org_keypair()
    try:
        CredentialStore().set("org", "private_key", priv.hex())
    except Exception as e:
        print(f"Error storing key in keyring: {e}", file=sys.stderr)
        return 1
    print(pub.hex())
    return 0


def _run_build(app_idea: str, output_dir: str) -> int:
    """Build a working repo from an app description (autonomous application builder)."""
    from devsper.dev.builder import run_build as do_build

    out = output_dir or "./build_output"
    print(f"Building app: {app_idea!r}", file=sys.stderr)
    print(f"Output directory: {out}", file=sys.stderr)
    result = do_build(app_idea, out)
    if result.get("success"):
        print(f"Done. Repository at: {result['repo_path']}", file=sys.stderr)
        print(result["repo_path"])
        return 0
    print("Build completed with test failures.", file=sys.stderr)
    dr = result.get("debug_result")
    if dr and getattr(dr, "last_stdout", None):
        print(dr.last_stdout[:1500], file=sys.stderr)
    return 1


def _run_replay(run_id: str, events_dir: str | None) -> int:
    """Replay a swarm run by run_id; if run_id empty, list recent run IDs."""
    from devsper.runtime.replay_engine import replay_run, list_run_ids

    if not run_id or not run_id.strip():
        try:
            from devsper.config import get_config

            cfg = get_config()
            events_dir = events_dir or cfg.events_dir
        except Exception:
            events_dir = events_dir or ".devsper/events"
        ids_ = list_run_ids(events_dir)
        if not ids_:
            print("No run logs found.", file=sys.stderr)
            return 0
        print("Recent run IDs (use: devsper replay <run_id>):")
        for i in ids_[:20]:
            print(f"  {i}")
        return 0
    try:
        from devsper.config import get_config

        cfg = get_config()
        events_dir = events_dir or cfg.events_dir
    except Exception:
        events_dir = events_dir or ".devsper/events"
    transcript = replay_run(run_id.strip(), events_dir=events_dir)
    print(transcript)
    if "No event log found" in transcript or "Empty event log" in transcript:
        return 1
    return 0


def _run_trace(run_id: str, events_dir: str | None) -> int:
    """Print trace-style hierarchy for one run from event logs."""
    from devsper.runtime.replay_engine import list_run_ids
    from devsper.runtime.trace_tree import render_trace_for_run

    try:
        from devsper.config import get_config

        cfg = get_config()
        events_dir = events_dir or cfg.events_dir
    except Exception:
        events_dir = events_dir or ".devsper/events"
    rid = (run_id or "").strip()
    if not rid:
        ids_ = list_run_ids(events_dir)
        if not ids_:
            print("No run logs found.", file=sys.stderr)
            return 1
        rid = ids_[0]
    out = render_trace_for_run(rid, events_dir)
    print(out)
    if out.startswith("No event log found") or out.startswith("Empty event log"):
        return 1
    return 0


def _run_budget(run_id: str, events_dir: str | None) -> int:
    from devsper.runtime.replay_engine import list_run_ids
    from devsper.server.topology import topology_snapshot

    try:
        from devsper.config import get_config

        cfg = get_config()
        events_dir = events_dir or cfg.events_dir
    except Exception:
        events_dir = events_dir or ".devsper/events"
    rid = (run_id or "").strip()
    if not rid:
        ids_ = list_run_ids(events_dir)
        if not ids_:
            print("No run logs found.", file=sys.stderr)
            return 1
        rid = ids_[0]
    snap = topology_snapshot(events_dir, rid)
    print(
        json.dumps(
            {
                "run_id": rid,
                "total_cost_usd": snap.get("summary", {}).get("total_cost_usd", 0.0),
                "tasks_done": snap.get("summary", {}).get("tasks_done", 0),
                "tasks_total": snap.get("summary", {}).get("tasks_total", 0),
            },
            indent=2,
        )
    )
    return 0


def _run_protocol_serve(host: str, port: int) -> int:
    from devsper.protocol.server import serve

    return serve(host=host, port=port)


def _run_events_api_serve(port: int, host: str, events_dir: str | None) -> int:
    from devsper.server.events import serve_api

    return serve_api(port=port, host=host, events_dir=events_dir or ".devsper/events")


def _run_export_package(name: str, out_dir: str) -> int:
    from devsper.cli.export import run_export_package

    return run_export_package(name=name, out_dir=out_dir)


def _run_run_package(path: str, task: str) -> int:
    from devsper.cli.export import run_package

    return run_package(package_path=path, task=task)


def _run_graph(run_id: str | None) -> int:
    """Export task DAG for a run as Mermaid diagram. run_id optional (latest if omitted)."""
    from devsper.config import get_config
    from devsper.visualization.dag_export import (
        load_dag,
        export_mermaid,
        list_run_ids,
    )

    cfg = get_config()
    events_dir = cfg.events_dir
    if run_id is None or run_id.strip() == "":
        run_ids = list_run_ids(events_dir)
        if not run_ids:
            print(
                'No runs found. Run a swarm first (e.g. devsper run "task").',
                file=sys.stderr,
            )
            return 1
        run_id = run_ids[0]
    nodes, edges = load_dag(events_dir, run_id.strip())
    if not nodes and not edges:
        print(f"No DAG found for run {run_id!r}.", file=sys.stderr)
        return 1
    print(export_mermaid(nodes, edges))
    return 0


def _run_analytics() -> int:
    """Show tool usage analytics: count, success rate, latency."""
    from devsper.analytics import get_default_analytics

    stats = get_default_analytics().get_stats()
    if not stats:
        print("No tool usage recorded yet.")
        return 0
    for s in stats:
        print(
            f"{s['tool_name']}: count={s['count']} success_rate={s['success_rate']:.1f}% avg_latency_ms={s['avg_latency_ms']}"
        )
    try:
        from devsper.tools.scoring import get_default_score_store
        from devsper.tools.scoring.report import generate_tools_report

        store = get_default_score_store()
        scores = store.get_all_scores()
        if scores:
            print()
            print(generate_tools_report(scores))
    except Exception:
        pass
    return 0


def _run_observe(port: int = 8501, db: str = "") -> int:
    """Launch the TruLens observability dashboard."""
    try:
        from devsper.telemetry.trulens import init_trulens, get_session
    except ImportError:
        print("TruLens is not installed. Run: uv pip install 'devsper[trulens]'")
        return 1

    session = get_session() or init_trulens(database_url=db)
    if session is None:
        print(
            "TruLens is not installed or failed to initialize.\n"
            "Run: uv pip install 'devsper[trulens]'"
        )
        return 1

    db_url = getattr(session, "connector", None)
    db_label = str(db or ".devsper/trulens.sqlite")
    print(f"Opening TruLens dashboard — db: {db_label}  port: {port}")
    print("Press Ctrl-C to stop.")
    try:
        session.run_dashboard(port=port)
    except KeyboardInterrupt:
        pass
    return 0


def _run_tools(args: object) -> int:
    """List tools with reliability scores, or reset score history."""
    from rich.console import Console
    from rich.prompt import Confirm
    from rich.table import Table

    from devsper.tools.registry import list_tools
    from devsper.tools.selector import _tool_category
    from devsper.tools.scoring import get_default_score_store
    from devsper.tools.scoring.scorer import score_label

    subcommand = getattr(args, "tools_subcommand", None) or "list"
    category_filter = getattr(args, "category", None)
    poor_only = getattr(args, "poor", False)
    reset_all = getattr(args, "reset_all", False)
    tool_name_reset = getattr(args, "tool_name", None)

    if subcommand == "reset":
        store = get_default_score_store()
        if reset_all:
            if not Confirm.ask("Wipe all tool scores? This cannot be undone."):
                return 0
            store.reset(None)
            print("All tool scores wiped.")
            return 0
        if tool_name_reset:
            store.reset(tool_name_reset)
            print(f"Score history wiped for: {tool_name_reset}")
            return 0
        print(
            "Usage: devsper tools reset <tool_name> | devsper tools reset --all",
            file=sys.stderr,
        )
        return 1

    # List: all registered tools with scores
    store = get_default_score_store()
    scores_by_name = {s.tool_name: s for s in store.get_all_scores()}
    all_tools = list_tools()
    if category_filter:
        allowed = {category_filter.lower().strip()}
        all_tools = [t for t in all_tools if _tool_category(t) in allowed]
    rows: list[tuple[str, str, float, str, float, float, int, str, bool]] = []
    for t in all_tools:
        s = scores_by_name.get(t.name)
        if s is None:
            score_val = 0.75
            label = "new"
            success_rate = 0.0
            avg_lat = 0.0
            calls = 0
            last_used = "-"
            is_new = True
        else:
            score_val = s.composite_score
            label = score_label(s.composite_score)
            success_rate = s.success_rate
            avg_lat = s.avg_latency_ms
            calls = s.total_calls
            last_used = (
                s.last_updated[:10] if len(s.last_updated) >= 10 else s.last_updated
            )
            is_new = s.is_new
        if poor_only and score_val >= 0.40:
            continue
        cat = _tool_category(t)
        rows.append(
            (
                t.name,
                cat,
                score_val,
                label,
                success_rate,
                avg_lat,
                calls,
                last_used,
                is_new,
            )
        )

    rows.sort(key=lambda r: -r[2])
    table = Table(title="Tool reliability scores")
    table.add_column("Tool Name", style="bold")
    table.add_column("Category")
    table.add_column("Score", justify="right")
    table.add_column("Label")
    table.add_column("Success Rate", justify="right")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Calls", justify="right")
    table.add_column("Last Used")
    for r in rows:
        name, cat, score_val, label, success_rate, avg_lat, calls, last_used, is_new = r
        if is_new and label == "new":
            label_style = "dim"
        elif label == "excellent":
            label_style = "green"
        elif label == "good":
            label_style = "default"
        elif label == "degraded":
            label_style = "yellow"
        else:
            label_style = "red"
        table.add_row(
            name,
            cat,
            f"{score_val:.2f}",
            f"[{label_style}]{label}[/]",
            f"{success_rate:.0%}" if not is_new else "-",
            f"{avg_lat:.0f} ms" if not is_new else "-",
            str(calls),
            last_used,
        )
    console = Console()
    if rows:
        console.print(table)
    else:
        console.print("No tools match the filters.")
    return 0


def _run_cache(subcommand: str, threshold: float | None = None) -> int:
    """Cache subcommand: stats | clear | tune."""
    from devsper.cache import TaskCache
    from pathlib import Path

    db_path = Path(".devsper") / "task_cache.db"
    cache = TaskCache()
    if subcommand == "stats":
        st = cache.stats()
        print(f"Cached task results (exact): {st['entries']}")
        try:
            from devsper.cache.store import get_default_cache_store

            store = get_default_cache_store(db_path)
            sst = store.stats()
            semantic_count = sst.get("semantic_entries", 0)
            if semantic_count > 0:
                try:
                    from devsper.config import get_config

                    cfg = get_config()
                    th = getattr(
                        getattr(cfg, "cache", None), "similarity_threshold", 0.92
                    )
                except Exception:
                    th = 0.92
                print(f"Semantic cache: enabled (threshold: {th})")
                print(f"Cache entries: {st['entries'] + semantic_count} tasks")
                print("Hit rate: N/A (run with semantic cache to collect)")
                print("Avg similarity: N/A")
                print("Est. tokens saved: N/A")
            else:
                print("Semantic cache: disabled or empty")
        except Exception:
            pass
        return 0
    if subcommand == "clear":
        cache.clear()
        try:
            from devsper.cache.store import get_default_cache_store

            get_default_cache_store(db_path).clear()
        except Exception:
            pass
        print("Cache cleared.")
        return 0
    if subcommand == "tune":
        try:
            from devsper.cache.task_cache import SemanticTaskCache
            from devsper.cache.embedding_index import _cosine_sim, bytes_to_embedding

            sem = SemanticTaskCache(
                similarity_threshold=threshold or 0.92,
                max_age_hours=168.0,
            )
            entries = sem.store.list_semantic_entries()
            if len(entries) < 2:
                print("Need at least 2 semantic cache entries to tune.")
                return 0
            # Use last 50
            entries = entries[-50:]
            # Load embeddings
            vecs = [bytes_to_embedding(e[0]) for e in entries]
            ths = [0.85, 0.88, 0.90, 0.92, 0.95]
            print("Threshold | Entries that would match self | Avg other-match count")
            print("----------|-------------------------------|----------------------")
            for th in ths:
                self_ok = sum(
                    1 for i in range(len(vecs)) if _cosine_sim(vecs[i], vecs[i]) >= th
                )
                other_count = 0
                for i in range(len(vecs)):
                    for j in range(len(vecs)):
                        if i != j and _cosine_sim(vecs[i], vecs[j]) >= th:
                            other_count += 1
                avg_other = other_count / len(vecs) if vecs else 0
                print(
                    f"  {th:.2f}     | {self_ok}/{len(vecs)}                          | {avg_other:.1f}"
                )
            return 0
        except Exception as e:
            print(f"Cache tune failed: {e}", file=sys.stderr)
            return 1
    print(
        "Usage: devsper cache stats | devsper cache clear | devsper cache tune [--threshold 0.90]",
        file=sys.stderr,
    )
    return 1


def _run_memory(limit: int) -> int:
    """List memory entries from the default store."""
    from devsper.memory.memory_store import get_default_store

    store = get_default_store()
    records = store.list_memory(limit=limit)
    if not records:
        print("No memory entries.")
        return 0
    for r in records:
        tags = ", ".join(r.tags[:8]) if r.tags else "-"
        summary = (r.content or "")[:200] + (
            "..." if len(r.content or "") > 200 else ""
        )
        print(f"[{r.memory_type.value}] {r.id}")
        print(f"  tags: {tags}")
        print(f"  {summary}")
        print()
    return 0


def _run_synthesize(
    query: str,
    no_kg: bool = False,
    json_out: bool = False,
    since: str | None = None,
) -> int:
    """Cross-run synthesis: answer query using all memory and optional KG."""
    import json
    from datetime import datetime, timezone
    from rich.console import Console
    from rich.panel import Panel
    from devsper.config import get_config
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex
    from devsper.knowledge.knowledge_graph import KnowledgeGraph
    from devsper.intelligence.synthesis import CrossRunSynthesizer
    from devsper.utils.models import resolve_model
    from devsper.providers.model_router import TaskType

    cfg = get_config()
    store = get_default_store()
    index = MemoryIndex(
        store=store,
        ranking_backend=getattr(cfg.memory, "backend", "local"),
    )
    worker_model = resolve_model(cfg.models.worker, TaskType.ANALYSIS)
    kg = None if no_kg else KnowledgeGraph(store=store)
    if kg and not no_kg:
        kg.load()
        kg.build_from_memory(merge=True)
    synthesizer = CrossRunSynthesizer(
        memory_index=index, knowledge_graph=kg, worker_model=worker_model
    )
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            pass
    out_chunks = []
    console = Console()
    if json_out:
        full = synthesizer.synthesize(
            query, max_sources=20, stream=False, use_kg=not no_kg, since=since_dt
        )
        answer = full if isinstance(full, str) else "".join(full)
        memories = index.query_across_runs(query, top_k=20, include_archived=False)
        if since_dt:
            memories = [m for m in memories if m.timestamp >= since_dt]
        run_ids = list(dict.fromkeys(getattr(m, "run_id", "") or "" for m in memories))
        run_ids = [r for r in run_ids if r]
        obj = {
            "query": query,
            "sources_used": len(memories),
            "run_ids": run_ids,
            "answer": answer,
        }
        print(json.dumps(obj, indent=2))
        return 0
    with console.status("Synthesizing..."):
        it = synthesizer.synthesize(
            query, max_sources=20, stream=True, use_kg=not no_kg, since=since_dt
        )
        for chunk in it:
            out_chunks.append(chunk)
            console.print(chunk, end="")
    console.print()
    memories = index.query_across_runs(query, top_k=20, include_archived=False)
    if since_dt:
        memories = [m for m in memories if m.timestamp >= since_dt]
    run_ids = list(dict.fromkeys(getattr(m, "run_id", "") or "" for m in memories))
    run_ids = [r for r in run_ids if r]
    console.print(
        Panel(
            f"Sources: {len(memories)} records across {len(run_ids)} runs\nRun IDs: {', '.join(run_ids[:15])}{'...' if len(run_ids) > 15 else ''}",
            title="Sources",
        )
    )
    return 0


def _run_memory_consolidate(dry_run: bool = False, min_cluster_size: int = 3) -> int:
    """Consolidate similar memory records: cluster, summarize, archive."""
    import asyncio
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn
    from devsper.config import get_config
    from devsper.memory.memory_store import get_default_store
    from devsper.memory.memory_index import MemoryIndex
    from devsper.memory.consolidation import MemoryConsolidator
    from devsper.utils.models import resolve_model
    from devsper.providers.model_router import TaskType

    store = get_default_store()
    cfg = get_config()
    index = MemoryIndex(
        store=store,
        ranking_backend=getattr(cfg.memory, "backend", "local"),
    )
    worker_model = resolve_model(cfg.models.worker, TaskType.ANALYSIS)
    consolidator = MemoryConsolidator(min_cluster_size=min_cluster_size)
    records = store.list_memory(limit=5000, include_archived=False)
    console = Console()
    console.print(f"Scanning {len(records)} memory records...")
    try:
        report = asyncio.get_event_loop().run_until_complete(
            consolidator.consolidate(store, index, worker_model, dry_run=dry_run)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        report = loop.run_until_complete(
            consolidator.consolidate(store, index, worker_model, dry_run=dry_run)
        )
    avg_per = (
        report.records_archived / report.clusters_consolidated
        if report.clusters_consolidated
        else 0
    )
    console.print(
        f"Found {report.clusters_found} clusters (avg {avg_per:.1f} records/cluster)"
    )
    console.print(
        f"Consolidating {report.clusters_consolidated} clusters with {min_cluster_size}+ records..."
    )
    with Progress(SpinnerColumn(), console=console) as progress:
        progress.add_task("consolidate", total=report.clusters_consolidated)
    console.print("Results:")
    console.print(f"  Records archived:   {report.records_archived}")
    console.print(f"  Summaries created:   {report.records_created}")
    console.print(f"  Est. tokens saved:   ~{report.tokens_saved_estimate} per run")
    if dry_run:
        console.print(
            "Run devsper memory consolidate without --dry-run to apply changes."
        )
    return 0


def _run_checkpoint_dispatch(args: object) -> int:
    if getattr(args, "checkpoint_cmd", None) == "restore":
        return _run_checkpoint_restore(getattr(args, "run_id", ""))
    return _run_checkpoint_list(args)


def _run_checkpoint_list(args: object) -> int:
    """List all checkpoint files with run_id, task counts, timestamp."""
    from devsper.config import get_config
    from devsper.swarm.checkpointer import SchedulerCheckpointer
    import os

    try:
        cfg = get_config()
        events_dir = getattr(cfg, "events_dir", ".devsper/events") or ".devsper/events"
    except Exception:
        events_dir = ".devsper/events"
    ckp = SchedulerCheckpointer(events_dir=events_dir)
    if not os.path.isdir(events_dir):
        print("No checkpoint directory found.")
        return 0
    found = []
    for name in os.listdir(events_dir):
        if name.endswith(".checkpoint.json"):
            run_id = name.replace(".checkpoint.json", "")
            path = os.path.join(events_dir, name)
            try:
                import json

                with open(path, "r") as f:
                    data = json.load(f)
                completed = data.get("completed_count", 0)
                failed = data.get("failed_count", 0)
                snapshot_at = data.get("snapshot_at", "")[:19]
                found.append((run_id, completed, failed, snapshot_at))
            except Exception:
                found.append((run_id, "?", "?", ""))
    if not found:
        print("No checkpoint files found.")
        return 0
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title="Checkpoints")
        table.add_column("Run ID", style="dim")
        table.add_column("Completed", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Snapshot at")
        for run_id, completed, failed, snapshot_at in sorted(
            found, key=lambda x: -len(x[0])
        ):
            table.add_row(run_id[:48], str(completed), str(failed), snapshot_at)
        console.print(table)
    except ImportError:
        for run_id, completed, failed, snapshot_at in found:
            print(f"{run_id}  completed={completed}  failed={failed}  {snapshot_at}")
    return 0


def _run_checkpoint_restore(run_id: str) -> int:
    """Restore a run from checkpoint and resume execution."""
    from devsper.config import get_config
    from devsper.swarm.checkpointer import SchedulerCheckpointer
    from devsper.types.exceptions import CheckpointNotFoundError

    if not run_id or not run_id.strip():
        print(
            "Error: run_id required. Use: devsper checkpoint restore <run_id>",
            file=sys.stderr,
        )
        return 1
    run_id = run_id.strip()
    try:
        cfg = get_config()
        events_dir = getattr(cfg, "events_dir", ".devsper/events") or ".devsper/events"
    except Exception:
        events_dir = ".devsper/events"
    ckp = SchedulerCheckpointer(events_dir=events_dir)
    try:
        scheduler = ckp.restore_or_raise(run_id)
    except CheckpointNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(
        f"Restored scheduler for run_id={run_id!r}: {len(scheduler.get_all_tasks())} tasks, {scheduler.get_results()} results."
    )
    print(
        "Resume execution is not yet implemented (1.10). Use checkpoint list to inspect state."
    )
    return 0


def _run_audit_dispatch(args: object) -> int:
    """Audit: print table, export, or verify."""
    from devsper.config import get_config
    from devsper.audit.logger import AuditLogger

    cmd = getattr(args, "audit_cmd", None)
    run_id = getattr(args, "run_id", None)
    export_fmt = getattr(args, "export", None)
    if cmd == "verify":
        run_id = getattr(args, "run_id", run_id)
        if not run_id:
            print("Error: run_id required for verify", file=sys.stderr)
            return 1
        cfg = get_config()
        ok, msg = AuditLogger.verify(run_id, cfg.data_dir)
        print(msg)
        return 0 if ok else 1
    if not run_id:
        print(
            "Error: run_id required (e.g. devsper audit events_2025-03-10...)",
            file=sys.stderr,
        )
        return 1
    cfg = get_config()
    logger = AuditLogger(cfg.data_dir, run_id=run_id)
    if export_fmt:
        out = logger.export(run_id, format=export_fmt)
        print(out)
        return 0
    out = logger.export(run_id, format="jsonl")
    if not out:
        print(f"No audit log for run_id={run_id}", file=sys.stderr)
        return 1
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=f"Audit log: {run_id}")
        table.add_column("timestamp")
        table.add_column("event_type")
        table.add_column("task_id")
        table.add_column("resource")
        table.add_column("success")
        for line in out.strip().split("\n"):
            if not line:
                continue
            import json

            r = json.loads(line)
            table.add_row(
                r.get("timestamp", "")[:19],
                r.get("event_type", ""),
                r.get("task_id", ""),
                r.get("resource", ""),
                str(r.get("success", "")),
            )
        console.print(table)
    except Exception:
        print(out)
    return 0


def _run_explain(args: object) -> int:
    """Explain: decision records for run or task."""
    run_id = getattr(args, "run_id", None)
    task_id = getattr(args, "task_id", None)
    if not run_id:
        print("Error: run_id required", file=sys.stderr)
        return 1
    try:
        from devsper.explainability.decision_tree import DecisionTreeBuilder
        from devsper.config import get_config

        cfg = get_config()
        events_dir = cfg.events_dir
        builder = DecisionTreeBuilder()
        records = builder.build_from_events(run_id, events_dir)
        if not records:
            print(f"No decision records for run_id={run_id}", file=sys.stderr)
            return 1
        if task_id:
            records = [r for r in records if r.task_id == task_id]
            if not records:
                print(f"No task {task_id} in run {run_id}", file=sys.stderr)
                return 1
        for r in records:
            print(f"--- {r.task_id} ---")
            print(f"  strategy: {r.strategy_selected}")
            print(f"  model: {r.model_selected} ({r.model_tier})")
            print(f"  tools: {r.tools_selected}")
            print(f"  confidence: {r.confidence:.0%}")
            print(
                f"  rationale: {r.rationale[:300]}..."
                if len(r.rationale or "") > 300
                else f"  rationale: {r.rationale}"
            )
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_simulate(args: object) -> int:
    """Simulate: dry-run planning, no LLM or tools."""
    import asyncio

    task = getattr(args, "task", "")
    cost_only = getattr(args, "cost_only", False) or getattr(args, "cost", False)
    if not task:
        print(
            'Error: task required (e.g. devsper simulate "Summarize X")',
            file=sys.stderr,
        )
        return 1
    try:
        from devsper.explainability.simulation import SimulationMode

        sim = SimulationMode()
        report = asyncio.run(sim.simulate(task))
        if cost_only:
            print(f"Estimated cost: {getattr(report, 'estimated_cost', 'N/A')}")
            return 0
        print(f"Tasks: {len(report.task_list)}")
        for t in report.task_list:
            print(f"  - {t}")
        print(f"Estimated cost: {getattr(report, 'estimated_cost', 'N/A')}")
        print(f"Estimated duration: {getattr(report, 'estimated_duration', 'N/A')}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _run_version(args: object) -> int:
    """Print installed devsper version. With global ``--json``, emit a small JSON object."""
    import platform

    try:
        from devsper import __version__ as ver_mod

        ver = str(ver_mod)
    except Exception:
        try:
            from importlib.metadata import version

            ver = version("devsper")
        except Exception:
            ver = "unknown"
    if getattr(args, "json_output", False):
        print(
            json.dumps(
                {
                    "version": ver,
                    "python": sys.version.split()[0],
                    "platform": platform.system(),
                }
            )
        )
    else:
        print(f"devsper {ver}")
    return 0


def _run_eval(args: object) -> int:
    """Eval harness: run dataset, score results, optionally optimize prompts."""
    import asyncio
    import json
    from pathlib import Path

    eval_cmd = getattr(args, "eval_cmd", None)

    if eval_cmd == "stub" or eval_cmd is None and not hasattr(args, "dataset"):
        # Generate stub dataset
        from devsper.evals.dataset import EvalDataset

        role = getattr(args, "role", "general")
        n = getattr(args, "n", 5)
        out = getattr(args, "out", None)
        dataset = EvalDataset.stub(role=role, n=n)
        if out:
            dataset.save(out)
            print(f"Stub dataset ({len(dataset)} cases) written to {out}")
        else:
            for case in dataset:
                print(json.dumps(case.to_dict()))
        return 0

    if eval_cmd == "results":
        from devsper.config import get_config

        try:
            results_dir = Path(getattr(args, "dir", None) or get_config().evals.results_dir)
        except Exception:
            results_dir = Path(".devsper/eval_results")
        if not results_dir.exists():
            print(f"No results found in {results_dir}")
            return 0
        files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            print("No eval result files found.")
            return 0
        for f in files[:20]:
            try:
                data = json.loads(f.read_text())
                print(
                    f"  {f.name}  role={data.get('role', '?')}  "
                    f"pass_rate={data.get('pass_rate', '?')}  "
                    f"mean_score={data.get('mean_score', '?')}"
                )
            except Exception:
                print(f"  {f.name}")
        return 0

    # eval_cmd == "run"
    from devsper.evals.dataset import EvalDataset
    from devsper.evals.metrics import get_metric
    from devsper.evals.runner import EvalRunner
    from devsper.config import get_config

    try:
        cfg = get_config()
    except Exception:
        from devsper.config.schema import devsperConfigModel
        cfg = devsperConfigModel()

    dataset_path = getattr(args, "dataset", None)
    if not dataset_path:
        print("Error: --dataset is required for 'eval run'")
        return 1

    dataset = EvalDataset.load(dataset_path)
    role = getattr(args, "role", None)
    metric_name = getattr(args, "metric", None) or cfg.evals.default_metric
    threshold = getattr(args, "threshold", None) or cfg.evals.pass_threshold
    concurrency = getattr(args, "concurrency", None) or cfg.evals.concurrency
    do_optimize = getattr(args, "optimize", False)
    optimizer_override = getattr(args, "optimizer", None)
    out_path = getattr(args, "out", None)

    metric = get_metric(metric_name)

    # Build optimizer if requested
    optimizer = None
    if do_optimize:
        from devsper.prompt_optimizer.factory import get_prompt_optimizer, reset_prompt_optimizer

        if optimizer_override:
            import os
            os.environ["DEVSPER_PROMPT_OPTIMIZER"] = optimizer_override
            reset_prompt_optimizer()
        optimizer = get_prompt_optimizer(cfg)

    # Build a minimal agent for evaluation
    from devsper.agents.agent import Agent

    agent = Agent(model_name=cfg.models.worker, use_tools=False)

    runner = EvalRunner(
        agent=agent,
        metric=metric,
        pass_threshold=threshold,
        concurrency=concurrency,
        optimize_after=do_optimize,
        optimizer=optimizer,
    )

    try:
        summary = asyncio.run(runner.run_async(dataset, role=role))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        summary = loop.run_until_complete(runner.run_async(dataset, role=role))

    # Print summary
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        console.print(
            f"\n[bold]Eval Results[/bold]  role=[cyan]{summary.role}[/cyan]  "
            f"metric=[cyan]{summary.metric_name}[/cyan]  "
            f"optimizer=[cyan]{summary.optimizer_backend}[/cyan]"
        )
        console.print(
            f"  Passed: [green]{summary.passed}[/green]/{summary.total}  "
            f"Pass rate: [bold]{summary.pass_rate:.1%}[/bold]  "
            f"Mean score: [bold]{summary.mean_score:.3f}[/bold]\n"
        )
        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="dim")
        table.add_column("Task", max_width=40)
        table.add_column("Score")
        table.add_column("Pass")
        for r in summary.results:
            color = "green" if r.passed else "red"
            table.add_row(
                r.case.id,
                r.case.task[:40],
                f"{r.score:.2f}",
                f"[{color}]{'✓' if r.passed else '✗'}[/{color}]",
            )
        console.print(table)
    except ImportError:
        print(f"\nEval: role={summary.role} metric={summary.metric_name}")
        print(f"  {summary.passed}/{summary.total} passed ({summary.pass_rate:.1%})")
        print(f"  Mean score: {summary.mean_score:.3f}")

    # Persist results
    results_dir = Path(cfg.evals.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = results_dir / f"eval_{summary.role}_{ts}.json"
    result_file.write_text(summary.to_json())
    print(f"\nResults saved to {result_file}")

    if out_path:
        Path(out_path).write_text(summary.to_json())

    return 0 if summary.pass_rate >= threshold else 1


def _run_health(args: object) -> int:
    """Run health checks. Exit 0 if healthy, 1 otherwise. Print ✓/✗ per check."""
    import asyncio
    from devsper.config import get_config
    from devsper.runtime.health import HealthChecker, HealthReport

    try:
        cfg = get_config()
    except Exception:
        cfg = None
    if cfg is None:
        print("No config loaded; using defaults for health checks.")
        from devsper.config.schema import devsperConfigModel

        cfg = devsperConfigModel()
    checker = HealthChecker()
    try:
        report = asyncio.run(checker.check(cfg))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        report = loop.run_until_complete(checker.check(cfg))
    try:
        from rich.console import Console

        console = Console()
        for name, ok in report.checks.items():
            if ok:
                console.print(f"  [green]✓[/green] {name}")
            else:
                console.print(f"  [red]✗[/red] {name}  {report.errors.get(name, '')}")
        if report.healthy:
            console.print("[green]healthy[/green]")
        else:
            console.print("[red]unhealthy[/red]")
    except ImportError:
        for name, ok in report.checks.items():
            sym = "✓" if ok else "✗"
            print(
                f"  {sym} {name}"
                + (f"  {report.errors.get(name, '')}" if not ok else "")
            )
        print("healthy" if report.healthy else "unhealthy")
    return 0 if report.healthy else 1


def _run_completion(parser: argparse.ArgumentParser, args: object) -> int:
    """Print shell completion script (bash, zsh, or fish)."""
    shell = getattr(args, "shell", "bash")
    try:
        import shtab

        if shell == "fish":
            try:
                from devsper.cli.ui import err_console

                err_console.print(
                    "[hive.warning]Fish completion: use shtab for bash/zsh; fish script can be generated from parser.[/]"
                )
            except ImportError:
                pass
            sys.stderr.write(
                "Fish completion: add 'complete -c devsper -a \"(devsper --print-completion 2>/dev/null)\"' or use shtab for bash/zsh\n"
            )
            return 0
        output = shtab.complete(parser, shell=shell)
        try:
            from devsper.cli.ui import console

            console.print(output, end="")
        except ImportError:
            print(output, end="")
        return 0
    except ImportError:
        try:
            from devsper.cli.ui import err_console

            err_console.print("Install shtab: pip install shtab")
        except ImportError:
            print("Install shtab: pip install shtab", file=sys.stderr)
        return 1


def _run_upgrade(args: object) -> int:
    """Run upgrade subcommand: check, changelog, install."""
    from devsper.upgrade.cli import run_upgrade

    return run_upgrade(args)


def _run_cloud_dispatch(args: object) -> int:
    """Devsper Cloud: login, run, status, logs."""
    cmd = getattr(args, "cloud_cmd", None)
    if not cmd:
        return 0
    from devsper.cli.commands.cloud import (
        cmd_cloud_login,
        cmd_cloud_logout,
        cmd_cloud_run,
        cmd_cloud_logs,
        cmd_cloud_status,
        cmd_cloud_respond,
        cmd_cloud_import_keys,
    )

    cmds = {
        "login": cmd_cloud_login,
        "logout": cmd_cloud_logout,
        "run": cmd_cloud_run,
        "status": cmd_cloud_status,
        "respond": cmd_cloud_respond,
        "logs": cmd_cloud_logs,
        "import-keys": cmd_cloud_import_keys,
    }
    if cmd in cmds:
        return cmds[cmd](args)
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].strip() == ".":
        sys.argv = [sys.argv[0]]

    # Non-blocking startup nag if update available (uses cache, ~100ms)
    try:
        from devsper.upgrade.notifier import check_and_notify

        check_and_notify()
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        prog="devsper",
        description="Orchestrate distributed swarms of AI agents that collaboratively solve complex tasks.",
        epilog="""
Quick start:
  devsper init                    # Set up a new project
  devsper run "your task here"    # Run the swarm
  devsper cloud login             # Authenticate to Devsper Cloud (optional)
  devsper tui                     # Launch the terminal UI

Examples:
  devsper run "Analyze diffusion models and summarize key papers"
  devsper cloud run "Summarize the README in three bullets."
  devsper build "fastapi todo app" -o ./myapp
  devsper credentials migrate     # Import API keys from .env
  devsper doctor                  # Check your setup
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    try:
        import shtab

        shtab.add_argument_to(parser, ["--print-completion"])
    except ImportError:
        pass
    global_grp = parser.add_argument_group("Global options")
    try:
        from devsper import __version__ as _cli_pkg_version

        _cli_version_str = str(_cli_pkg_version)
    except Exception:
        _cli_version_str = "unknown"
    global_grp.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {_cli_version_str}",
        help="Print devsper version and exit",
    )
    global_grp.add_argument(
        "--debug", action="store_true", help="Enable DEBUG log level"
    )
    global_grp.add_argument(
        "--trace", action="store_true", help="Enable TRACE log level (very verbose)"
    )
    global_grp.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="WARN and above only, suppress progress",
    )
    global_grp.add_argument(
        "--no-color", action="store_true", help="Disable color output"
    )
    global_grp.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Machine-readable JSON output",
    )
    global_grp.add_argument(
        "--plain", action="store_true", help="Plain text output, no Rich (for piping)"
    )
    global_grp.add_argument(
        "--new",
        action="store_true",
        help="Start a new REPL session (discard previous conversation history)",
    )
    global_grp.add_argument(
        "--session",
        metavar="ID",
        default=None,
        help="Resume a specific REPL session by ID",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    run_parser = subparsers.add_parser(
        "run",
        help="Run the swarm on a task",
        description="Decompose a task into subtasks and execute them with AI workers.",
        epilog="""
Examples:
  devsper run "Summarize swarm intelligence in one paragraph"
  devsper run "Analyze diffusion models" -q
  devsper run --reporter "task"   # headless; set DEVSPER_PLATFORM_RUN_ID + REDIS_URL for live platform SSE
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.add_argument(
        "task",
        nargs="?",
        default="Summarize swarm intelligence in one paragraph.",
        help="Task prompt",
    )
    run_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="No progress output; only print results (for piping)",
    )
    run_parser.add_argument(
        "--summary",
        action="store_true",
        help="Only print run summary, not task results",
    )
    run_parser.add_argument(
        "--shadow",
        action="store_true",
        help="Run runtime and platform paths and print side-by-side comparison.",
    )
    run_parser.add_argument(
        "--project-id",
        default="",
        help="Optional project id for platform run compatibility.",
    )
    run_parser.add_argument(
        "--manifest-file",
        default="",
        help="Path to JSON manifest to attach to platform run.",
    )
    run_parser.add_argument(
        "--platform-timeout",
        type=float,
        default=180.0,
        help="Platform run polling timeout seconds.",
    )
    run_parser.add_argument(
        "--platform-poll-interval",
        type=float,
        default=2.0,
        help="Platform polling interval seconds.",
    )
    run_parser.add_argument(
        "--reporter",
        action="store_true",
        help="Headless integration: skip TUI; stream events via DEVSPER_PLATFORM_RUN_ID + REDIS_URL "
        "and/or DEVSPER_PLATFORM_RUNTIME_EVENTS (see docs).",
    )
    run_parser.set_defaults(func=lambda a: _run_swarm(a))

    meta_parser = subparsers.add_parser(
        "meta",
        help="Run meta-planner: decompose mega-task into sub-swarms and run them",
        description="Decompose a mega-task into sub-swarms with dependencies and SLAs.",
    )
    meta_parser.add_argument(
        "mega_task",
        nargs="?",
        default="",
        help="Mega-task to run (e.g. 'Research and implement a todo API')",
    )
    meta_parser.add_argument(
        "--max-swarms", type=int, default=None, help="Max sub-swarms to run"
    )
    meta_parser.add_argument(
        "--budget", type=float, default=None, help="Max budget in USD"
    )
    meta_sub = meta_parser.add_subparsers(dest="meta_cmd", help="Meta subcommands")
    meta_plan_p = meta_sub.add_parser(
        "plan", help="Decompose only; print SubSwarmSpecs as table"
    )
    meta_plan_p.add_argument("mega_task", help="Mega-task to decompose")
    meta_plan_p.set_defaults(
        meta_cmd="plan", func=lambda a: _run_meta_plan(a.mega_task)
    )
    meta_parser.set_defaults(
        meta_cmd=None,
        func=lambda a: _run_meta(
            a.mega_task or "Summarize the state of AI in 2024",
            getattr(a, "max_swarms", None),
            getattr(a, "budget", None),
        ),
    )

    approvals_parser = subparsers.add_parser(
        "approvals",
        help="Human-in-the-loop approval requests",
        description="List, show, approve, or reject pending approval requests.",
    )
    approvals_sub = approvals_parser.add_subparsers(
        dest="approvals_cmd", help="Approval subcommands"
    )
    approvals_list_p = approvals_sub.add_parser(
        "list", help="Table of pending approvals"
    )
    approvals_list_p.set_defaults(func=lambda a: _run_approvals_list())
    approvals_show_p = approvals_sub.add_parser(
        "show", help="Show full approval request"
    )
    approvals_show_p.add_argument("request_id", help="Request ID")
    approvals_show_p.set_defaults(func=lambda a: _run_approvals_show(a.request_id))
    approvals_approve_p = approvals_sub.add_parser("approve", help="Approve a request")
    approvals_approve_p.add_argument("request_id", help="Request ID")
    approvals_approve_p.add_argument(
        "--notes", type=str, default="", help="Reviewer notes"
    )
    approvals_approve_p.set_defaults(
        func=lambda a: _run_approvals_approve(a.request_id, getattr(a, "notes", ""))
    )
    approvals_reject_p = approvals_sub.add_parser("reject", help="Reject a request")
    approvals_reject_p.add_argument("request_id", help="Request ID")
    approvals_reject_p.add_argument(
        "--notes", type=str, default="", help="Reviewer notes"
    )
    approvals_reject_p.set_defaults(
        func=lambda a: _run_approvals_reject(a.request_id, getattr(a, "notes", ""))
    )
    approvals_watch_p = approvals_sub.add_parser(
        "watch", help="Live-updating table of pending approvals (10s refresh)"
    )
    approvals_watch_p.set_defaults(func=lambda a: _run_approvals_watch())
    approvals_parser.set_defaults(
        approvals_cmd="list", func=lambda a: _run_approvals_list()
    )

    tui_parser = subparsers.add_parser(
        "tui",
        help="Launch terminal UI",
        description="Interactive dashboard for runs, memory, and analytics.",
        epilog="""
Examples:
  devsper tui
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tui_parser.set_defaults(func=lambda a: _run_tui())

    research_parser = subparsers.add_parser(
        "research",
        help="Run literature review on a directory",
        description="Run the literature review example on a directory of papers.",
        epilog="""
Examples:
  devsper research .
  devsper research ./papers
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    research_parser.add_argument(
        "path", nargs="?", default=".", help="Directory with papers (PDF/DOCX)"
    )
    research_parser.set_defaults(func=lambda a: _run_research(a.path))

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a swarm run or repository",
        description="With a run_id: build run report and optional LLM analysis. With a path: repository analysis.",
        epilog="""
Examples:
  devsper analyze events_2025-03-09...     # run analysis
  devsper analyze events_xxx --no-ai --json
  devsper analyze .                        # repo analysis
  devsper analyze /path/to/repo
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analyze_parser.add_argument(
        "run_id_or_path",
        nargs="?",
        default=None,
        help="Run ID (e.g. events_...) for run analysis, or path (e.g. .) for repo analysis",
    )
    analyze_parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip LLM analysis (run analysis only)",
    )
    analyze_parser.add_argument(
        "--json",
        action="store_true",
        dest="analyze_json",
        help="Output RunReport as JSON (run analysis only)",
    )
    analyze_parser.set_defaults(func=_run_analyze_dispatch)

    run_analyze_parser = subparsers.add_parser(
        "run-analyze",
        help="Analyze a swarm run by run_id",
        description="Build run report from event log, optional LLM analysis.",
        epilog="""
Examples:
  devsper run-analyze events_2025-03-09...
  devsper run-analyze events_2025-03-09... --no-ai
  devsper run-analyze events_2025-03-09... --json
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_analyze_parser.add_argument("run_id", help="Run ID (e.g. from devsper runs)")
    run_analyze_parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip LLM analysis (stats only, no API call)",
    )
    run_analyze_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output raw RunReport as JSON",
    )
    run_analyze_parser.set_defaults(
        func=lambda a: _run_analyze_run(a.run_id, a.no_ai, a.json_output)
    )

    runs_parser = subparsers.add_parser(
        "runs",
        help="List run history or show run summary",
        description="List recent runs (or filter by --failed). With run_id: same as run-analyze <run_id> --no-ai.",
        epilog="""
Examples:
  devsper runs
  devsper runs --limit 10 --failed
  devsper runs --json
  devsper runs events_2025-03-09...
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    runs_parser.add_argument(
        "run_id",
        nargs="?",
        default=None,
        help="If given: show report for this run (no AI, same as run-analyze <run_id> --no-ai)",
    )
    runs_parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=20,
        help="Max runs to list (default 20)",
    )
    runs_parser.add_argument(
        "--failed",
        action="store_true",
        help="Only list runs with failed_tasks > 0",
    )
    runs_parser.add_argument(
        "--json",
        action="store_true",
        dest="runs_json",
        help="Output runs list as JSON",
    )
    runs_parser.set_defaults(func=_run_runs)

    export_parser = subparsers.add_parser(
        "export-runs",
        help="Export all run history into multi-format artifacts",
        description="Export run history from DB + events into markdown/docx/latex/rst/bibtex and optional PDF outputs.",
    )
    export_parser.add_argument(
        "--output",
        "-o",
        default="",
        help="Output directory (default .devsper/exports/runs_<timestamp>)",
    )
    export_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of recent runs to include (default: all)",
    )
    export_parser.add_argument(
        "--pdf-pipeline",
        choices=["latex", "html", "both"],
        default="both",
        help="PDF generation pipeline(s) to run",
    )
    export_parser.set_defaults(func=_run_export_runs)

    memory_parser = subparsers.add_parser(
        "memory",
        help="List memory or consolidate",
        description="List stored memory entries or consolidate similar records.",
        epilog="""
Examples:
  devsper memory
  devsper memory -n 50
  devsper memory consolidate [--dry-run] [--min-cluster-size 3]
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    memory_parser.add_argument(
        "--limit", "-n", type=int, default=20, help="Max entries to show (for list)"
    )
    memory_sub = memory_parser.add_subparsers(
        dest="memory_cmd", help="memory subcommand"
    )
    memory_list_p = memory_sub.add_parser("list", help="List memory entries (default)")
    memory_list_p.add_argument(
        "--limit", "-n", type=int, default=20, help="Max entries"
    )
    memory_list_p.set_defaults(func=lambda a: _run_memory(getattr(a, "limit", 20)))
    memory_parser.set_defaults(
        memory_cmd="list", func=lambda a: _run_memory(getattr(a, "limit", 20))
    )
    memory_consolidate_p = memory_sub.add_parser(
        "consolidate", help="Cluster and summarize similar memories"
    )
    memory_consolidate_p.add_argument(
        "--dry-run", action="store_true", help="Preview without writing"
    )
    memory_consolidate_p.add_argument(
        "--min-cluster-size",
        type=int,
        default=3,
        help="Min records per cluster (default 3)",
    )
    memory_consolidate_p.set_defaults(
        func=lambda a: _run_memory_consolidate(
            getattr(a, "dry_run", False), getattr(a, "min_cluster_size", 3)
        )
    )

    synthesize_parser = subparsers.add_parser(
        "synthesize",
        help="Cross-run synthesis",
        description="Answer a question using all memory (and optional knowledge graph) across runs.",
        epilog="""
Examples:
  devsper synthesize "What have I learned about rate limiting in APIs?"
  devsper synthesize "Summarize findings about transformer architectures" --no-kg
  devsper synthesize "What datasets have I worked with?" --json
  devsper synthesize "Recent findings" --since 2025-01-01
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    synthesize_parser.add_argument("query", help="Question to synthesize from memory")
    synthesize_parser.add_argument(
        "--no-kg", action="store_true", help="Skip knowledge graph, use memory only"
    )
    synthesize_parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON: query, sources_used, run_ids, answer",
    )
    synthesize_parser.add_argument(
        "--since", metavar="DATE", help="Filter memory to records after date (ISO)"
    )
    synthesize_parser.set_defaults(
        func=lambda a: _run_synthesize(
            a.query, a.no_kg, a.json, getattr(a, "since", None)
        )
    )

    query_parser = subparsers.add_parser(
        "query",
        help="Query knowledge graph",
        description="Search entities and relationships in the knowledge graph built from memory.",
        epilog="""
Examples:
  devsper query "diffusion models"
  devsper query "machine learning"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    query_parser.add_argument(
        "query_text",
        nargs="?",
        default="",
        help="Query string (e.g. diffusion models)",
    )
    query_parser.set_defaults(func=lambda a: _run_query(a.query_text))

    workflow_parser = subparsers.add_parser(
        "workflow",
        help="List, validate, or run workflows",
        description="List, validate, or run workflows from workflow.devsper.toml.",
        epilog="""
Examples:
  devsper workflow list
  devsper workflow validate my_workflow
  devsper workflow run my_workflow --input text="hello"
  devsper workflow my_workflow
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    workflow_parser.add_argument(
        "first",
        nargs="?",
        help="Subcommand: list | validate | run; or workflow name to run",
    )
    workflow_parser.add_argument(
        "second",
        nargs="?",
        help="Workflow name (for validate/run)",
    )
    workflow_parser.add_argument(
        "--input",
        action="append",
        metavar="KEY=VALUE",
        help="Runtime input (repeat for multiple). Used with run.",
    )
    workflow_parser.set_defaults(func=_workflow_dispatch)

    init_parser = subparsers.add_parser(
        "init",
        help="Set up a new project",
        description="Create devsper.toml, configure providers, and optionally store API keys securely.",
        epilog="""
Examples:
  devsper init
  devsper init -y
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    init_parser.add_argument(
        "--no-interactive",
        "-y",
        action="store_true",
        help="Use defaults without prompting (e.g. for CI)",
    )
    init_parser.add_argument(
        "--md",
        action="store_true",
        help="Generate a devsper.md project instructions file using an LLM",
    )
    init_parser.set_defaults(func=lambda a: _run_init_md() if getattr(a, "md", False) else _run_init(a.no_interactive))

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Verify environment",
        description="Check API keys, config files, tool registry, and security (e.g. plaintext keys in TOML).",
        epilog="""
Examples:
  devsper doctor
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    doctor_parser.set_defaults(func=lambda a: _run_doctor())

    mcp_parser = subparsers.add_parser(
        "mcp",
        help="MCP server commands (list, test, add)",
        description="List configured MCP servers, test connection, or add a server interactively.",
    )
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_cmd", help="Subcommand")
    mcp_list_p = mcp_sub.add_parser("list", help="List MCP servers and tool counts")
    mcp_list_p.set_defaults(func=lambda a: _run_mcp_list())
    mcp_test_p = mcp_sub.add_parser("test", help="Test connection to an MCP server")
    mcp_test_p.add_argument("server_name", help="Server name from config")
    mcp_test_p.set_defaults(func=lambda a: _run_mcp_test(a.server_name))
    mcp_add_p = mcp_sub.add_parser(
        "add", help="Interactively add an MCP server to devsper.toml"
    )
    mcp_add_p.set_defaults(func=lambda a: _run_mcp_add())
    mcp_parser.set_defaults(mcp_cmd="list", func=lambda a: _run_mcp_list())

    a2a_parser = subparsers.add_parser(
        "a2a",
        help="A2A agent commands (serve, discover, call)",
        description="Run A2A server, discover external agents, or call an agent with a task.",
    )
    a2a_sub = a2a_parser.add_subparsers(dest="a2a_cmd", help="Subcommand")
    a2a_serve_p = a2a_sub.add_parser("serve", help="Start A2A server")
    a2a_serve_p.add_argument(
        "--port", type=int, default=None, help="Port (default: config or 8080)"
    )
    a2a_serve_p.set_defaults(func=lambda a: _run_a2a_serve(getattr(a, "port", None)))
    a2a_discover_p = a2a_sub.add_parser(
        "discover", help="Fetch AgentCard from URL, print skills"
    )
    a2a_discover_p.add_argument("url", help="Agent URL (e.g. http://localhost:8080)")
    a2a_discover_p.set_defaults(func=lambda a: _run_a2a_discover(a.url))
    a2a_call_p = a2a_sub.add_parser(
        "call", help="Send task to external A2A agent, stream output"
    )
    a2a_call_p.add_argument("url", help="Agent URL")
    a2a_call_p.add_argument("task", help="Task text to send")
    a2a_call_p.set_defaults(func=lambda a: _run_a2a_call(a.url, a.task))
    a2a_parser.set_defaults(a2a_cmd=None, func=lambda a: a2a_parser.print_help() or 0)

    node_parser = subparsers.add_parser(
        "node",
        help="Distributed node commands (v1.10)",
        description="Start a node, query status, drain workers, stream events.",
    )
    node_sub = node_parser.add_subparsers(dest="node_cmd", help="Subcommand")
    node_start_p = node_sub.add_parser("start", help="Start a node in the foreground")
    node_start_p.add_argument(
        "--role",
        choices=["controller", "worker", "hybrid"],
        default="hybrid",
        help="Node role",
    )
    node_start_p.add_argument("--port", type=int, default=None, help="RPC port")
    node_start_p.add_argument(
        "--workers", type=int, default=None, help="Max workers (worker node)"
    )
    node_start_p.add_argument(
        "--tags", type=str, default="", help="Comma-separated tags e.g. gpu,high-mem"
    )
    node_start_p.set_defaults(func=lambda a: _run_node_start(a))
    node_status_p = node_sub.add_parser("status", help="Query controller status")
    node_status_p.add_argument(
        "--controller-url", type=str, default=None, help="Controller RPC URL"
    )
    node_status_p.set_defaults(func=lambda a: _run_node_status(a))
    node_workers_p = node_sub.add_parser("workers", help="List workers from controller")
    node_workers_p.add_argument("--controller-url", type=str, default=None)
    node_workers_p.set_defaults(func=lambda a: _run_node_workers(a))
    node_drain_p = node_sub.add_parser("drain", help="Drain a worker (stop new tasks)")
    node_drain_p.add_argument("node_id", help="Worker node ID")
    node_drain_p.add_argument("--controller-url", type=str, default=None)
    node_drain_p.set_defaults(func=lambda a: _run_node_drain(a))
    node_logs_p = node_sub.add_parser("logs", help="Stream events from controller")
    node_logs_p.add_argument(
        "--follow", action="store_true", help="Keep connection open"
    )
    node_logs_p.add_argument("--controller-url", type=str, default=None)
    node_logs_p.set_defaults(func=lambda a: _run_node_logs(a))

    pool_parser = subparsers.add_parser(
        "pool",
        help="Worker pool commands (v2.x)",
        description="Inspect and run the platform worker pool manager.",
    )
    pool_sub = pool_parser.add_subparsers(dest="pool_cmd", help="Subcommand")
    pool_status_p = pool_sub.add_parser("status", help="Show worker counts by tier")
    pool_status_p.add_argument(
        "--redis-url", type=str, default=None, help="Redis URL override"
    )
    pool_status_p.set_defaults(func=lambda a: _run_pool_status(a))
    pool_workers_p = pool_sub.add_parser("workers", help="List workers by tier")
    pool_workers_p.add_argument(
        "--redis-url", type=str, default=None, help="Redis URL override"
    )
    pool_workers_p.set_defaults(func=lambda a: _run_pool_workers(a))
    pool_queue_p = pool_sub.add_parser("queue", help="Show wait queue depth")
    pool_queue_p.set_defaults(func=lambda a: _run_pool_queue(a))
    pool_start_p = pool_sub.add_parser(
        "start", help="Start local worker pool (foreground)"
    )
    pool_start_p.add_argument("--local", action="store_true", help="Start local pool")
    pool_start_p.add_argument(
        "--workers", type=int, default=2, help="Number of local workers"
    )
    pool_start_p.set_defaults(func=lambda a: _run_pool_start(a))
    pool_parser.set_defaults(
        pool_cmd=None, func=lambda a: pool_parser.print_help() or 0
    )

    org_parser = subparsers.add_parser(
        "org",
        help="Org management (pool + keys)",
        description="Org-scoped operations for pool and E2EE keys.",
    )
    org_sub = org_parser.add_subparsers(dest="org_cmd", help="Subcommand")
    org_keygen_p = org_sub.add_parser(
        "keygen", help="Generate org E2EE keypair (store private in keyring)"
    )
    org_keygen_p.set_defaults(func=lambda a: _run_org_keygen(a))
    org_parser.set_defaults(org_cmd=None, func=lambda a: org_parser.print_help() or 0)

    platform_parser = subparsers.add_parser(
        "platform",
        help="Platform migration and conversion commands",
        description="Connect runtime users to platform and track migration ROI.",
    )
    platform_sub = platform_parser.add_subparsers(
        dest="platform_cmd", help="Subcommand"
    )
    platform_connect_p = platform_sub.add_parser(
        "connect",
        help="One-command onboarding bridge to platform.",
    )
    platform_connect_p.add_argument(
        "--api-url", default=None, help="Platform API base URL"
    )
    platform_connect_p.add_argument("--org", default=None, help="Platform org slug")
    platform_connect_p.add_argument("--token", default=None, help="Platform JWT token")
    platform_connect_p.add_argument(
        "--skip-toml",
        action="store_true",
        help="Do not update local devsper.toml memory config",
    )
    platform_connect_p.set_defaults(func=lambda a: _run_platform_connect(a))
    platform_roi_p = platform_sub.add_parser(
        "roi", help="Show conversion funnel counters"
    )
    platform_roi_p.set_defaults(func=lambda a: _run_platform_roi())
    platform_parser.set_defaults(
        platform_cmd=None, func=lambda a: platform_parser.print_help() or 0
    )

    graph_parser = subparsers.add_parser(
        "graph",
        help="Export task DAG as Mermaid",
        description="Export the task dependency graph for a run as a Mermaid diagram.",
        epilog="""
Examples:
  devsper graph
  devsper graph abc123-run-id
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    graph_parser.add_argument(
        "run_id",
        nargs="?",
        default=None,
        help="Run ID (default: latest)",
    )
    graph_parser.set_defaults(func=lambda a: _run_graph(a.run_id))

    trace_parser = subparsers.add_parser(
        "trace",
        help="Print span tree for a run",
        description="Pretty-print a trace-style tree for a run using the event log.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    trace_parser.add_argument(
        "run_id",
        nargs="?",
        default="",
        help="Run ID (default: latest)",
    )
    trace_parser.add_argument(
        "--events-dir",
        default=None,
        help="Events directory (default: config)",
    )
    trace_parser.set_defaults(func=lambda a: _run_trace(a.run_id, a.events_dir))

    budget_parser = subparsers.add_parser(
        "budget",
        help="Show run budget/cost summary",
        description="Show cost summary for a run from event logs.",
    )
    budget_parser.add_argument(
        "run_id", nargs="?", default="", help="Run ID (default: latest)"
    )
    budget_parser.add_argument("--events-dir", default=None, help="Events directory")
    budget_parser.set_defaults(func=lambda a: _run_budget(a.run_id, a.events_dir))

    serve_parser = subparsers.add_parser(
        "serve",
        help="Serve polyglot agent protocol",
        description="Start HTTP protocol server (/health, /agent, /agent/execute).",
    )
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.set_defaults(func=lambda a: _run_protocol_serve(a.host, a.port))

    serve_api_parser = subparsers.add_parser(
        "serve-api",
        help="Serve events/topology API",
        description="Start sidecar API for runs/events/topology.",
    )
    serve_api_parser.add_argument("--host", default="0.0.0.0")
    serve_api_parser.add_argument("--port", type=int, default=7474)
    serve_api_parser.add_argument("--events-dir", default=None)
    serve_api_parser.set_defaults(
        func=lambda a: _run_events_api_serve(a.port, a.host, a.events_dir)
    )

    export_pkg_parser = subparsers.add_parser(
        "export",
        help="Export deployable agent package",
        description="Create a .devsper package.",
    )
    export_pkg_parser.add_argument("--name", default="my-agent")
    export_pkg_parser.add_argument("--out", default="./dist")
    export_pkg_parser.set_defaults(func=lambda a: _run_export_package(a.name, a.out))

    run_pkg_parser = subparsers.add_parser(
        "run-package",
        help="Run exported .devsper package",
    )
    run_pkg_parser.add_argument("package_path")
    run_pkg_parser.add_argument("task")
    run_pkg_parser.set_defaults(func=lambda a: _run_run_package(a.package_path, a.task))

    analytics_parser = subparsers.add_parser(
        "analytics",
        help="Show tool usage analytics",
        description="Display tool usage stats: count, success rate, and latency.",
        epilog="""
Examples:
  devsper analytics
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    analytics_parser.set_defaults(func=lambda a: _run_analytics())

    tools_parser = subparsers.add_parser(
        "tools",
        help="List tool reliability scores or reset history",
        description="List registered tools with reliability scores (excellent/good/degraded/poor), or reset score history.",
        epilog="""
Examples:
  devsper tools
  devsper tools --category research
  devsper tools --poor
  devsper tools reset my_tool
  devsper tools reset --all
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tools_parser.add_argument(
        "tools_subcommand",
        nargs="?",
        default="list",
        choices=["list", "reset"],
        help="list (default) | reset",
    )
    tools_parser.add_argument(
        "tool_name",
        nargs="?",
        help="Tool name (for reset)",
    )
    tools_parser.add_argument(
        "--category",
        metavar="NAME",
        help="Filter by category",
    )
    tools_parser.add_argument(
        "--poor",
        action="store_true",
        help="Show only tools with score < 0.40",
    )
    tools_parser.add_argument(
        "--all",
        dest="reset_all",
        action="store_true",
        help="Wipe all scores (with confirmation; use with reset)",
    )
    tools_parser.set_defaults(func=_run_tools)

    cache_parser = subparsers.add_parser(
        "cache",
        help="Task result cache",
        description="View or clear the task result cache.",
        epilog="""
Examples:
  devsper cache stats
  devsper cache clear
  devsper cache tune [--threshold 0.90]
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cache_parser.add_argument(
        "subcommand",
        nargs="?",
        default="stats",
        choices=["stats", "clear", "tune"],
        help="stats | clear | tune",
    )
    cache_parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Similarity threshold for tune (e.g. 0.90)",
    )
    cache_parser.set_defaults(
        func=lambda a: _run_cache(a.subcommand, getattr(a, "threshold", None))
    )

    build_parser = subparsers.add_parser(
        "build",
        help="Build an app from a description",
        description="Autonomous application builder: generate a working repo from an app description.",
        epilog="""
Examples:
  devsper build "fastapi todo app"
  devsper build "CLI tool for CSV analysis" -o ./csv-tool
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    build_parser.add_argument(
        "app_idea",
        nargs="?",
        default="fastapi todo app",
        help="App description (e.g. 'fastapi todo app')",
    )
    build_parser.add_argument(
        "-o",
        "--output",
        default="./build_output",
        help="Output directory for the generated repo (default: ./build_output)",
    )
    build_parser.set_defaults(func=lambda a: _run_build(a.app_idea, a.output))

    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay a swarm run",
        description="Reconstruct swarm execution from the event log (deterministic replay).",
        epilog="""
Examples:
  devsper replay
  devsper replay abc123-run-id
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    replay_parser.add_argument(
        "run_id",
        nargs="?",
        default="",
        help="Run ID (from events log filename); list recent if omitted",
    )
    replay_parser.add_argument(
        "--events-dir",
        default=None,
        help="Events directory (default: config)",
    )
    replay_parser.set_defaults(func=lambda a: _run_replay(a.run_id, a.events_dir))

    credentials_parser = subparsers.add_parser(
        "credentials",
        help="Manage API keys and credentials",
        description="Store, list, and migrate credentials securely (OS keychain only).",
        epilog="""
Examples:
  devsper credentials set openai api_key
  devsper credentials set azure endpoint \"https://.../openai/v1\"
  devsper credentials list
  devsper credentials migrate
  devsper credentials export azure    # print env KEY=value for sourcing
  devsper credentials delete openai api_key
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    credentials_parser.add_argument(
        "credentials_subcommand",
        nargs="?",
        choices=["set", "list", "delete", "migrate", "export"],
        help="set | list | delete | migrate | export",
    )
    credentials_parser.add_argument(
        "provider",
        nargs="?",
        help="Provider (e.g. openai, anthropic)",
    )
    credentials_parser.add_argument(
        "key",
        nargs="?",
        help="Key name (e.g. api_key)",
    )
    credentials_parser.add_argument(
        "value",
        nargs="?",
        help="Value (for set only). Omit to be prompted, or pipe: echo 'val' | devsper credentials set azure endpoint",
    )
    credentials_parser.set_defaults(func=lambda a: _run_credentials(a))

    cloud_parser = subparsers.add_parser(
        "cloud",
        help="Devsper Cloud: login, queue runs, poll status",
        description="Authenticate to the hosted platform API and submit background jobs.",
        epilog="""
Examples:
  devsper cloud login --api-url http://localhost:8080 --email you@example.com
  devsper cloud run "Summarize the platform README in three bullets."
  devsper cloud status <run_id>
  devsper cloud respond <run_id> --request-id <uuid> --answers '{"Q":"A"}'
  devsper cloud logs <run_id>
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cloud_sub = cloud_parser.add_subparsers(dest="cloud_cmd", help="Subcommand")

    cloud_login_p = cloud_sub.add_parser(
        "login", help="Login (stores JWT in OS keychain)"
    )
    cloud_login_p.add_argument(
        "--api-url",
        default=None,
        help="Platform API base URL (default: http://localhost:8080 or keyring)",
    )
    cloud_login_p.add_argument("--email", default=None, help="Account email")
    cloud_login_p.add_argument(
        "--password", default=None, help="Password (omit to be prompted)"
    )
    cloud_login_p.add_argument(
        "--org", default=None, help="Default org slug (default: personal org from /me)"
    )
    cloud_login_p.set_defaults(cloud_cmd="login")

    cloud_logout_p = cloud_sub.add_parser(
        "logout", help="Clear stored cloud credentials"
    )
    cloud_logout_p.set_defaults(cloud_cmd="logout")

    cloud_import_keys_p = cloud_sub.add_parser(
        "import-keys", help="Import local API keys to the platform organization"
    )
    cloud_import_keys_p.add_argument(
        "provider", nargs="?", help="Specific provider to import (e.g. openai)"
    )
    cloud_import_keys_p.add_argument(
        "--api-url", default=None, help="Override platform API URL"
    )
    cloud_import_keys_p.add_argument("--org", default=None, help="Override org slug")
    cloud_import_keys_p.add_argument("--token", default=None, help="Override JWT")
    cloud_import_keys_p.set_defaults(cloud_cmd="import-keys")

    cloud_run_p = cloud_sub.add_parser(
        "run", help="Submit a task and wait for completion"
    )
    cloud_run_p.add_argument("task", help="Natural language task")
    cloud_run_p.add_argument(
        "--api-url", default=None, help="Override platform API URL"
    )
    cloud_run_p.add_argument("--org", default=None, help="Override org slug")
    cloud_run_p.add_argument(
        "--token", default=None, help="Override JWT (default: keyring)"
    )
    cloud_run_p.add_argument("--project-id", default="", help="Optional project UUID")
    cloud_run_p.add_argument(
        "--manifest", default="", help="JSON file merged into run manifest"
    )
    cloud_run_p.add_argument(
        "--workflow",
        default="",
        help="Workflow name from workflow.devsper.toml (snapshot embedded in manifest)",
    )
    cloud_run_p.add_argument(
        "--config", default="", help="JSON file merged into run config"
    )
    cloud_run_p.add_argument(
        "--manifest-version",
        default=None,
        help="Optional x-devsper-run-manifest-version header",
    )
    cloud_run_p.add_argument(
        "--no-wait", "--detach", action="store_true", help="Print run_id only; do not poll"
    )
    cloud_run_p.add_argument(
        "--timeout", type=float, default=300.0, help="Poll timeout seconds"
    )
    cloud_run_p.add_argument(
        "--interval", type=float, default=2.0, help="Poll interval seconds"
    )
    cloud_run_p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Machine-readable output",
    )
    cloud_run_p.set_defaults(cloud_cmd="run")

    cloud_status_p = cloud_sub.add_parser("status", help="Show run snapshot")
    cloud_status_p.add_argument("run_id", help="Run UUID")
    cloud_status_p.add_argument(
        "--api-url", default=None, help="Override platform API URL"
    )
    cloud_status_p.add_argument("--org", default=None, help="Override org slug")
    cloud_status_p.add_argument("--token", default=None, help="Override JWT")
    cloud_status_p.add_argument(
        "--json", action="store_true", dest="json_output", help="Print full JSON"
    )
    cloud_status_p.set_defaults(cloud_cmd="status")

    cloud_respond_p = cloud_sub.add_parser(
        "respond",
        help="Send a human-in-the-loop answer for a waiting cloud run",
    )
    cloud_respond_p.add_argument("run_id", help="Run UUID")
    cloud_respond_p.add_argument(
        "--request-id",
        required=True,
        help="Clarification request_id from run stream or logs",
    )
    cloud_respond_p.add_argument(
        "--answers",
        dest="answers_json",
        default="",
        help='JSON object of answers, keys = field questions (e.g. \'{"Which API?":"REST"}\')',
    )
    cloud_respond_p.add_argument(
        "--skipped",
        action="store_true",
        help="Tell the worker to proceed with defaults / without user answers",
    )
    cloud_respond_p.add_argument(
        "--api-url", default=None, help="Override platform API URL"
    )
    cloud_respond_p.add_argument("--org", default=None, help="Override org slug")
    cloud_respond_p.add_argument("--token", default=None, help="Override JWT")
    cloud_respond_p.set_defaults(cloud_cmd="respond")

    cloud_logs_p = cloud_sub.add_parser("logs", help="List run events (history)")
    cloud_logs_p.add_argument("run_id", help="Run UUID")
    cloud_logs_p.add_argument(
        "--api-url", default=None, help="Override platform API URL"
    )
    cloud_logs_p.add_argument("--org", default=None, help="Override org slug")
    cloud_logs_p.add_argument("--token", default=None, help="Override JWT")
    cloud_logs_p.add_argument(
        "--json", action="store_true", dest="json_output", help="Print raw JSON"
    )
    cloud_logs_p.set_defaults(cloud_cmd="logs")

    cloud_parser.set_defaults(func=_run_cloud_dispatch)

    completion_parser = subparsers.add_parser(
        "completion",
        help="Generate shell completion script",
        description="Print shell completion script for bash or zsh. Add to your shell config to enable tab completion.",
        epilog="""
Examples:
  # Bash - add to ~/.bashrc or ~/.bash_profile
  eval "$(devsper completion bash)"

  # Zsh - add to ~/.zshrc
  eval "$(devsper completion zsh)"

  # Or install to a file (bash)
  devsper completion bash > ~/.local/share/bash-completion/completions/devsper
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    completion_parser.add_argument(
        "shell",
        choices=["bash", "zsh", "fish"],
        help="Shell type (bash, zsh, or fish)",
    )
    completion_parser.set_defaults(func=lambda a: _run_completion(parser, a))

    upgrade_parser = subparsers.add_parser(
        "upgrade",
        help="Check for updates and upgrade",
        description="Check for updates and upgrade devsper from PyPI.",
        epilog="""
Examples:
  devsper upgrade
  devsper upgrade --check
  devsper upgrade -y
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    upgrade_parser.add_argument(
        "--check",
        action="store_true",
        help="Only check and display if update is available",
    )
    upgrade_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    upgrade_parser.add_argument(
        "--version",
        metavar="VERSION",
        default=None,
        help="Install a specific version (e.g. 1.2.3)",
    )
    upgrade_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without installing",
    )
    upgrade_parser.set_defaults(func=_run_upgrade)

    checkpoint_parser = subparsers.add_parser(
        "checkpoint",
        help="List checkpoints or restore a run",
        description="List checkpoint files or restore a run from checkpoint and resume.",
    )
    checkpoint_sub = checkpoint_parser.add_subparsers(
        dest="checkpoint_cmd", help="Subcommand"
    )
    checkpoint_list_p = checkpoint_sub.add_parser(
        "list", help="List all checkpoint files"
    )
    checkpoint_list_p.set_defaults(func=_run_checkpoint_dispatch)
    checkpoint_restore_p = checkpoint_sub.add_parser(
        "restore", help="Restore run from checkpoint"
    )
    checkpoint_restore_p.add_argument("run_id", help="Run ID to restore")
    checkpoint_restore_p.set_defaults(func=_run_checkpoint_dispatch)
    checkpoint_parser.set_defaults(checkpoint_cmd="list", func=_run_checkpoint_dispatch)

    audit_parser = subparsers.add_parser(
        "audit",
        help="View or export audit log for a run",
        description="Print audit log as table, export to CSV/JSONL, or verify chain integrity.",
    )
    audit_parser.add_argument(
        "run_id", nargs="?", default=None, help="Run ID (e.g. events_...)"
    )
    audit_parser.add_argument(
        "--export", choices=["jsonl", "csv", "siem"], default=None, help="Export format"
    )
    audit_sub = audit_parser.add_subparsers(dest="audit_cmd", help="Subcommand")
    audit_verify_p = audit_sub.add_parser(
        "verify", help="Verify audit log chain integrity"
    )
    audit_verify_p.add_argument("run_id", help="Run ID to verify")
    audit_verify_p.set_defaults(audit_cmd="verify")
    audit_parser.set_defaults(func=_run_audit_dispatch)

    explain_parser = subparsers.add_parser(
        "explain",
        help="Show decision records for a run or task",
        description="Print decision tree and rationale for agent actions.",
    )
    explain_parser.add_argument("run_id", help="Run ID")
    explain_parser.add_argument(
        "task_id", nargs="?", default=None, help="Optional task ID for single task"
    )
    explain_parser.set_defaults(func=_run_explain)

    simulate_parser = subparsers.add_parser(
        "simulate",
        help="Dry-run planning without LLM or tool execution",
        description="Run planner and scheduler only; output task list and cost estimate.",
    )
    simulate_parser.add_argument("task", help="Root task description")
    simulate_parser.add_argument(
        "--cost", action="store_true", help="Print cost estimate only"
    )
    simulate_parser.set_defaults(func=_run_simulate)

    version_parser = subparsers.add_parser(
        "version",
        help="Print devsper version",
        description="Print the installed devsper package version. Use global --json for machine-readable output.",
        epilog="""
Examples:
  devsper version
  devsper --json version
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    version_parser.set_defaults(func=_run_version)

    observe_parser = subparsers.add_parser(
        "observe",
        help="Launch TruLens observability dashboard",
        description="Open the TruLens dashboard for browsing run records, traces, and feedback.",
        epilog="""
Examples:
  devsper observe
  devsper observe --port 8502
  devsper observe --db sqlite:///custom.sqlite
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    observe_parser.add_argument(
        "--port", type=int, default=8501, help="Dashboard port (default: 8501)"
    )
    observe_parser.add_argument(
        "--db",
        default="",
        metavar="URL",
        help="TruLens database URL (default: sqlite:///.devsper/trulens.sqlite)",
    )
    observe_parser.set_defaults(func=lambda a: _run_observe(a.port, a.db))

    eval_parser = subparsers.add_parser(
        "eval",
        help="Eval harness and prompt optimization",
        description="Run evals against a JSONL dataset and optionally optimize prompts.",
        epilog="""
Examples:
  devsper eval run --dataset evals.jsonl --metric contains
  devsper eval run --dataset evals.jsonl --role research --optimize --optimizer dspy
  devsper eval stub --role research --out evals.jsonl
  devsper eval results
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    eval_sub = eval_parser.add_subparsers(dest="eval_cmd", help="Subcommand")

    eval_run_p = eval_sub.add_parser("run", help="Run eval dataset")
    eval_run_p.add_argument("--dataset", required=True, help="Path to JSONL dataset")
    eval_run_p.add_argument("--role", default=None, help="Filter to this agent role")
    eval_run_p.add_argument(
        "--metric",
        default=None,
        help="Metric name: exact_match | contains | regex_match | word_overlap | llm_judge (default: config)",
    )
    eval_run_p.add_argument(
        "--threshold", type=float, default=None, help="Pass threshold (default: config)"
    )
    eval_run_p.add_argument(
        "--optimize",
        action="store_true",
        help="Run prompt optimization after eval using the configured optimizer",
    )
    eval_run_p.add_argument(
        "--optimizer",
        default=None,
        help="Override optimizer backend: noop | dspy | gepa",
    )
    eval_run_p.add_argument(
        "--concurrency", type=int, default=None, help="Parallel eval cases"
    )
    eval_run_p.add_argument("--out", default=None, help="Save JSON results to this path")
    eval_run_p.set_defaults(eval_cmd="run")

    eval_stub_p = eval_sub.add_parser("stub", help="Generate a stub dataset")
    eval_stub_p.add_argument(
        "--role", default="general", help="Agent role (research/code/analysis/general)"
    )
    eval_stub_p.add_argument("-n", type=int, default=5, help="Number of examples")
    eval_stub_p.add_argument(
        "--out", default=None, help="Output JSONL path (default: prints to stdout)"
    )
    eval_stub_p.set_defaults(eval_cmd="stub")

    eval_results_p = eval_sub.add_parser("results", help="List recent eval result files")
    eval_results_p.add_argument("--dir", default=None, help="Results directory")
    eval_results_p.set_defaults(eval_cmd="results")

    eval_parser.set_defaults(func=_run_eval)

    health_parser = subparsers.add_parser(
        "health",
        help="Health and readiness check",
        description="Run health checks (bus, memory, tools, KG, checkpoint dir). Exit 0 if healthy, 1 otherwise.",
    )
    health_parser.set_defaults(func=_run_health)

    _load_project_dotenv()
    args = parser.parse_args()
    # Apply global CLI options
    no_color = getattr(args, "no_color", False) or os.environ.get("NO_COLOR")
    plain = getattr(args, "plain", False) or (not sys.stdout.isatty())
    try:
        from devsper.cli.ui import reconfigure_console, set_log_level

        reconfigure_console(
            no_color=bool(no_color), force_terminal=False if plain else None
        )
        if getattr(args, "trace", False):
            set_log_level("trace")
        elif getattr(args, "debug", False):
            set_log_level("debug")
        elif getattr(args, "quiet", False):
            set_log_level("warn")
        else:
            set_log_level("info")
    except ImportError:
        pass
    if not args.command:
        return _run_repl(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
