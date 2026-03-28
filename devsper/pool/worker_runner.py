from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from devsper.pool.crypto import decrypt_payload


def _get_org_private_key_bytes() -> bytes:
    profile = (os.getenv("DEVSPER_PROFILE") or "prod").strip().lower()
    if profile == "local" and os.getenv("DEVSPER_ORG_PRIVATE_KEY"):
        return bytes.fromhex(os.environ["DEVSPER_ORG_PRIVATE_KEY"])
    try:
        from devsper.credentials.store import CredentialStore

        v = CredentialStore().get("org", "private_key")
        if not v:
            raise RuntimeError("missing org private key in keyring")
        return bytes.fromhex(v)
    except Exception as e:
        raise RuntimeError(f"cannot load org private key: {e}") from e


async def _run():
    worker_id = os.environ.get("DEVSPER_WORKER_ID") or ""
    if not worker_id:
        print("DEVSPER_WORKER_ID required", file=sys.stderr)
        raise SystemExit(2)

    redis_url = os.environ.get("REDIS_URL") or "redis://localhost:6379"
    import redis.asyncio as aioredis

    r = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = r.pubsub()
    channel = f"devsper:worker:{worker_id}"
    await pubsub.subscribe(channel)

    org_priv = _get_org_private_key_bytes()

    from devsper.agents.agent import Agent, AgentRequest
    from devsper.types.task import Task

    agent = Agent(use_tools=True)

    msg: dict | None = None
    async for raw in pubsub.listen():
        if raw.get("type") != "message":
            continue
        payload = raw.get("data")
        if not payload:
            continue
        try:
            msg = payload if isinstance(payload, dict) else json.loads(payload)
            if msg.get("event") != "task.assigned":
                continue
            task_id = msg["task_id"]
            ct = bytes.fromhex(msg["payload_enc"])
            pt = decrypt_payload(ct, org_priv)
            task_payload = json.loads(pt)
            prompt = task_payload.get("prompt") or task_payload.get("task") or ""
            req = AgentRequest(
                task=Task(id=task_id, description=str(prompt)),
                memory_context=str(task_payload.get("context") or ""),
                tools=list(task_payload.get("tools") or []),
                model=str(task_payload.get("model") or "mock"),
                system_prompt=str(task_payload.get("system_prompt") or ""),
                prefetch_used=False,
            )
            t0 = time.time()
            resp = agent.run(req)  # sync
            out = resp.to_dict()
            out["worker_id"] = worker_id
            out["duration_seconds"] = float(time.time() - t0)
            await r.publish(f"devsper:task:{task_id}:result", json.dumps(out))
        except Exception as e:
            try:
                tid = (msg or {}).get("task_id", "")
                await r.publish(
                    f"devsper:task:{tid}:result",
                    json.dumps({"success": False, "error": str(e), "worker_id": worker_id}),
                )
            except Exception:
                pass


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()

