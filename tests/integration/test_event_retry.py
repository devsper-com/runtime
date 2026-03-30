import json
import os
import tempfile
import time
from datetime import datetime, timezone

from devsper.platform.runtime_events import PlatformRuntimeEventSink, PlatformRuntimeSinkConfig
from devsper.types.event import Event, events


def test_platform_runtime_event_sink_writes_wal_on_failure():
    with tempfile.TemporaryDirectory() as td:
        wal_path = os.path.join(td, "wal.jsonl")

        cfg = PlatformRuntimeSinkConfig(
            api_base_url="http://127.0.0.1:1",  # fail fast / refuse connection
            internal_secret="secret",
            platform_run_id="run-1",
            platform_trace_id="trace-1",
            redis_url="",  # disable redis stream
            progress_interval_ms=1000,
            queue_maxsize=2,
            http_timeout_s=0.2,
        )
        sink = PlatformRuntimeEventSink(cfg, wal_path=wal_path)
        try:
            # Burst a few events; HTTP delivery will fail so WAL append should happen.
            for _ in range(10):
                sink.on_devsper_event(
                    Event(
                        timestamp=datetime.now(timezone.utc),
                        type=events.SWARM_STARTED,
                        payload={"user_task": "x"},
                    )
                )

            # Give background thread time to process/fail.
            time.sleep(0.6)

            sink.close(timeout_s=1.0)

            assert os.path.exists(wal_path)
            with open(wal_path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            assert len(lines) > 0
            sample = json.loads(lines[0])
            assert sample.get("event_type") in ("run_started", "step_started", "run_progress", "tool_called", "run_completed", "run_failed")
            assert sample.get("run_id") == "run-1"
        finally:
            try:
                sink.close(timeout_s=0.2)
            except Exception:
                pass

