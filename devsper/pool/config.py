from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib


@dataclass
class PoolConfig:
    profile: str = "prod"
    redis_url: str = "redis://localhost:6379"
    max_tasks_per_minute: int = 60
    heartbeat_interval: int = 30
    worker_timeout_secs: int = 90
    max_payload_bytes: int = 1_048_576
    max_queue_depth: int = 100
    local_workers: int = 0
    local_worker_cmd: str = "devsper-worker"


def load_pool_config(profile_override: str | None = None) -> PoolConfig:
    profile = (profile_override or os.getenv("DEVSPER_PROFILE") or "").strip().lower() or "prod"
    profile_path = Path(__file__).resolve().parent / "profiles" / f"{profile}.toml"
    if not profile_path.exists():
        profile = "prod"
        profile_path = Path(__file__).resolve().parent / "profiles" / "prod.toml"

    data = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    pool = data.get("pool", {})
    limits = pool.get("limits", {}) if isinstance(pool.get("limits"), dict) else data.get("pool.limits", {})
    # Our profile TOML uses [pool.limits] etc; tomllib nests them inside pool dict as "limits"
    limits = pool.get("limits", {})

    return PoolConfig(
        profile=pool.get("profile", profile),
        redis_url=pool.get("redis_url", "redis://localhost:6379"),
        max_tasks_per_minute=int(pool.get("max_tasks_per_minute", 60)),
        heartbeat_interval=int(pool.get("heartbeat_interval", 30)),
        worker_timeout_secs=int(pool.get("worker_timeout_secs", 90)),
        max_payload_bytes=int(limits.get("max_payload_bytes", 1_048_576)),
        max_queue_depth=int(limits.get("max_queue_depth", 100)),
        local_workers=int(pool.get("local_workers", 0)),
        local_worker_cmd=str(pool.get("local_worker_cmd", "python -m devsper.agents.run_agent")),
    )

