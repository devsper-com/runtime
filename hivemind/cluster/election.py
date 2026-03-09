"""Leader election via Redis SET NX + TTL."""

import asyncio
from typing import Callable

LEADER_KEY_PREFIX = "hivemind:leader:"
LEADER_TTL = 15
REFRESH_INTERVAL = 5


class LeaderElector:
    """Distributed leader election. Key: hivemind:leader:{run_id}, value: node_id, TTL 15s."""

    def __init__(self, redis_client: object, run_id: str) -> None:
        self._redis = redis_client
        self._run_id = run_id
        self._key = f"{LEADER_KEY_PREFIX}{run_id}"

    async def campaign(self, node_id: str) -> bool:
        """SET key node_id NX EX 15. Returns True if this node won."""
        try:
            return await self._redis.set(
                self._key, node_id, nx=True, ex=LEADER_TTL
            )
        except Exception:
            return False

    async def refresh(self, node_id: str) -> bool:
        """Atomic: if current value == node_id, EXPIRE 15 and return True."""
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('EXPIRE', KEYS[1], ARGV[2])
            return 1
        else
            return 0
        end
        """
        try:
            result = await self._redis.eval(script, 1, self._key, node_id, LEADER_TTL)
            return bool(result)
        except Exception:
            return False

    async def get_leader(self) -> str | None:
        raw = await self._redis.get(self._key)
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    async def abdicate(self, node_id: str) -> None:
        script = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('DEL', KEYS[1])
        end
        """
        try:
            await self._redis.eval(script, 1, self._key, node_id)
        except Exception:
            pass

    async def watch(
        self,
        node_id: str,
        on_elected: Callable[[], object],
        on_lost: Callable[[], object],
    ) -> None:
        """Loop every 5s: refresh if leader, else campaign; call on_elected/on_lost on transition."""
        currently_leader = False
        while True:
            try:
                await asyncio.sleep(REFRESH_INTERVAL)
                if currently_leader:
                    if await self.refresh(node_id):
                        continue
                    currently_leader = False
                    await on_lost()
                else:
                    if await self.campaign(node_id):
                        currently_leader = True
                        await on_elected()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
