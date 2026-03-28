"""
Integration: Redis + PoolManager publish/subscribe (same paths as local profile).

Requires Redis on REDIS_URL (default redis://127.0.0.1:6379). Skips if unreachable.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from devsper.pool.config import load_pool_config
from devsper.pool.crypto import decrypt_payload, encrypt_payload, generate_org_keypair
from devsper.pool.manager import PoolManager
from devsper.pool.models import PoolTier, QueuedTask, WorkerRecord, WorkerStatus
from devsper.pool.store import RedisPoolStore


async def _redis_ping(url: str) -> bool:
    import redis.asyncio as aioredis

    try:
        r = aioredis.from_url(url, decode_responses=True)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False


def test_enqueue_local_worker_receives_encrypted_task():
    async def _run():
        redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
        if not await _redis_ping(redis_url):
            pytest.skip(f"Redis not reachable at {redis_url}")

        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url, decode_responses=True)
        await r.flushdb()

        cfg = load_pool_config("local")
        priv_b, pub_b = generate_org_keypair()

        task_id = "e2e-task-1"
        payload = {"task_id": task_id, "prompt": "2+2", "context": "", "tools": [], "model": "mock", "system_prompt": ""}
        payload_enc = encrypt_payload(json.dumps(payload).encode(), pub_b)

        class _Bus:
            def __init__(self, url: str):
                import redis as sync_redis

                self._r = sync_redis.Redis.from_url(url, decode_responses=True)

            def publish(self, channel: str, body: dict):
                self._r.publish(channel, json.dumps(body))

        store = RedisPoolStore(redis_url)
        pool = PoolManager(store=store, bus=_Bus(redis_url), config=cfg)

        wid = "e2e-worker-1"
        await store.save_worker(
            WorkerRecord(
                worker_id=wid,
                node_id="local",
                org_id=None,
                tier=PoolTier.LOCAL,
                status=WorkerStatus.IDLE,
                profile="local",
            )
        )
        await store.heartbeat(wid, ttl_secs=90)

        pubsub = r.pubsub()
        await pubsub.subscribe(f"devsper:worker:{wid}")
        # Subscribe before publish; Redis drops messages with no subscribers.
        await asyncio.sleep(0.05)

        qt = QueuedTask(task_id=task_id, org_id="local-org", user_id="u1", priority=1, payload_enc=payload_enc)
        await pool.enqueue(qt)

        got = None
        for _ in range(50):
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
            if msg and msg.get("type") == "message":
                got = json.loads(msg["data"])
                break
        await pubsub.unsubscribe(f"devsper:worker:{wid}")
        await r.aclose()

        assert got is not None, "expected task.assigned on worker channel"
        assert got.get("event") == "task.assigned"
        ct = bytes.fromhex(got["payload_enc"])
        pt = decrypt_payload(ct, priv_b)
        assert json.loads(pt.decode())["prompt"] == "2+2"

    asyncio.run(_run())
