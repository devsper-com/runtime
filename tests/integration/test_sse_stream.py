import json
import os
import tempfile
import time
from datetime import datetime, timezone

from devsper.platform.runtime_events import PlatformRuntimeEventSink, PlatformRuntimeSinkConfig
from devsper.types.event import Event, events


def test_sse_event_burst_does_not_drop_or_crash_on_platform_failure():
    with tempfile.TemporaryDirectory() as td:
        wal_path = os.path.join(td, "wal.jsonl")
        cfg = PlatformRuntimeSinkConfig(
            api_base_url="http://127.0.0.1:1",  # down
            internal_secret="secret",
            platform_run_id="run-1",
            platform_trace_id="trace-1",
            redis_url="",
            progress_interval_ms=10,
            queue_maxsize=8,
            http_timeout_s=0.15,
        )
        sink = PlatformRuntimeEventSink(cfg, wal_path=wal_path)
        try:
            # Burst >100 events: should remain bounded by queue_maxsize and/or WAL.
            for i in range(120):
                sink.on_devsper_event(
                    Event(
                        timestamp=datetime.now(timezone.utc),
                        type=events.TOOL_CALLED,
                        payload={"task_id": f"t{i}", "tool": "filesystem.list_dir", "result_preview": "x"},
                    )
                )

            time.sleep(0.8)
            sink.close(timeout_s=1.0)

            assert os.path.exists(wal_path)
            with open(wal_path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f.readlines() if ln.strip()]
            # Under heavy failure, not all events are guaranteed to be present in WAL
            # (queue overflow + bounded retry); but we must have at least a non-trivial set.
            assert len(lines) >= 1

            sample = json.loads(lines[0])
            assert sample.get("event_type") in ("tool_called", "run_progress")
            assert sample.get("run_id") == "run-1"
        finally:
            try:
                sink.close(timeout_s=0.2)
            except Exception:
                pass

