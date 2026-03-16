"""Cluster registry backed by Redis hash."""

from devsper.cluster.node_info import NodeInfo, NodeRole

REGISTRY_KEY_PREFIX = "devsper:cluster:"
REGISTRY_NODES_SUFFIX = ":nodes"
REGISTRY_TTL = 60


class ClusterRegistry:
    """Backed by Redis hash: devsper:cluster:{run_id}:nodes. TTL 60s refreshed by heartbeat."""

    def __init__(self, redis_client: object, run_id: str) -> None:
        self._redis = redis_client
        self._run_id = run_id
        self._key = f"{REGISTRY_KEY_PREFIX}{run_id}{REGISTRY_NODES_SUFFIX}"

    async def register(self, node: NodeInfo) -> None:
        await self._redis.hset(self._key, node.node_id, node.to_json())
        await self._redis.expire(self._key, REGISTRY_TTL)

    async def heartbeat(self, node_id: str, updates: dict) -> None:
        node = await self.get_node(node_id)
        if node is None:
            return
        d = node.to_dict()
        d.update(updates)
        updated = NodeInfo.from_dict(d)
        await self._redis.hset(self._key, node_id, updated.to_json())
        await self._redis.expire(self._key, REGISTRY_TTL)

    async def deregister(self, node_id: str) -> None:
        await self._redis.hdel(self._key, node_id)

    async def get_all(self) -> list[NodeInfo]:
        raw = await self._redis.hgetall(self._key)
        out: list[NodeInfo] = []
        for _k, v in raw.items():
            val = v.decode("utf-8") if isinstance(v, bytes) else v
            try:
                out.append(NodeInfo.from_json(val))
            except Exception:
                pass
        return out

    async def get_node(self, node_id: str) -> NodeInfo | None:
        raw = await self._redis.hget(self._key, node_id)
        if raw is None:
            return None
        val = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            return NodeInfo.from_json(val)
        except Exception:
            return None

    async def get_controllers(self) -> list[NodeInfo]:
        all_nodes = await self.get_all()
        return [
            n for n in all_nodes
            if n.role in (NodeRole.CONTROLLER, NodeRole.HYBRID)
        ]

    async def get_workers(self) -> list[NodeInfo]:
        all_nodes = await self.get_all()
        return [
            n for n in all_nodes
            if n.role in (NodeRole.WORKER, NodeRole.HYBRID)
        ]

    async def is_healthy(self) -> bool:
        return len(await self.get_controllers()) >= 1
