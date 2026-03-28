from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
import logging
import shlex
import sys

from .models import PoolTier, WorkerRecord, WorkerStatus
from .manager import PoolManager
from .store import RedisPoolStore, InMemoryPoolStore
from .config import load_pool_config

log = logging.getLogger("devsper.local_pool")


class LocalWorkerPool:
    def __init__(self, pool, config, redis_url: str):
        self.pool = pool
        self.config = config
        self._redis_url = redis_url
        self._procs: dict[str, subprocess.Popen] = {}

    async def start(self, n: int | None = None):
        n = n or getattr(self.config, "local_workers", 0) or 0
        for _ in range(n):
            await self._spawn_worker()

    async def _spawn_worker(self):
        worker_id = str(uuid.uuid4())
        env = {
            **os.environ,
            "DEVSPER_WORKER_ID": worker_id,
            "DEVSPER_PROFILE": "local",
            # Workers must use the same Redis as registration / `devsper run` (defaults differ per module).
            "REDIS_URL": self._redis_url,
        }
        cmd = shlex.split(str(getattr(self.config, "local_worker_cmd", "") or ""))
        if not cmd:
            cmd = ["python", "-c", "import time; time.sleep(3600)"]
        if cmd and cmd[0] in ("python", "python3"):
            cmd[0] = sys.executable
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._procs[worker_id] = proc

        org_id = os.environ.get("DEVSPER_ORG_ID") or getattr(self.config, "org_id", None)
        worker = WorkerRecord(
            worker_id=worker_id,
            node_id="local",
            org_id=org_id,
            tier=PoolTier.LOCAL,
            status=WorkerStatus.IDLE,
            profile="local",
        )
        await self.pool.register_worker(worker)
        asyncio.create_task(self._monitor(worker_id, proc))

    async def _monitor(self, worker_id: str, proc: subprocess.Popen):
        while True:
            await asyncio.sleep(5)
            if proc.poll() is not None:
                await self.pool.deregister_worker(worker_id)
                self._procs.pop(worker_id, None)
                await self._spawn_worker()
                return
            await self.pool.store.heartbeat(worker_id, ttl_secs=getattr(self.config, "worker_timeout_secs", 90))

    async def stop(self):
        for wid, proc in list(self._procs.items()):
            try:
                proc.terminate()
            except Exception:
                pass
            await self.pool.deregister_worker(wid)
        self._procs.clear()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Start local worker pool (dev/test).")
    parser.add_argument("--workers", type=int, default=None, help="Number of local workers to spawn")
    args = parser.parse_args()

    if not os.getenv("DEVSPER_PROFILE"):
        os.environ["DEVSPER_PROFILE"] = "local"
    cfg = load_pool_config()
    # Prefer REDIS_URL env override for local dev/compose.
    redis_url = os.getenv("REDIS_URL") or cfg.redis_url
    os.environ.setdefault("REDIS_URL", redis_url)

    use_memory = (os.getenv("DEVSPER_POOL_BACKEND", "").strip().lower() == "memory")
    if use_memory:
        store: RedisPoolStore | InMemoryPoolStore = InMemoryPoolStore()
        log.warning("DEVSPER_POOL_BACKEND=memory: workers are in-process only; use TCP Redis for real E2E.")
    else:
        store = RedisPoolStore(redis_url)

    class _Bus:
        def __init__(self, url: str):
            import redis as sync_redis

            self._r = sync_redis.Redis.from_url(url, decode_responses=True)

        def publish(self, channel: str, payload: dict):
            import json as _json

            self._r.publish(channel, _json.dumps(payload))

    pool = PoolManager(store=store, bus=_Bus(redis_url), config=cfg)
    lp = LocalWorkerPool(pool, cfg, redis_url=redis_url)

    async def run():
        await lp.start(args.workers)
        # Run forever.
        while True:
            await asyncio.sleep(60)

    asyncio.run(run())


if __name__ == "__main__":
    main()

