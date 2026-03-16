"""In-memory registry and elector for single-node mode (no Redis)."""

import asyncio
from devsper.cluster.node_info import NodeInfo, NodeRole
from devsper.cluster.registry import ClusterRegistry
from devsper.cluster.election import LeaderElector


class InMemoryRegistry:
    """Registry backed by a dict. Single-node only."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._nodes: dict[str, str] = {}

    async def register(self, node: NodeInfo) -> None:
        self._nodes[node.node_id] = node.to_json()

    async def heartbeat(self, node_id: str, updates: dict) -> None:
        if node_id not in self._nodes:
            return
        import json
        data = json.loads(self._nodes[node_id])
        data.update(updates)
        self._nodes[node_id] = json.dumps(data)

    async def deregister(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)

    async def get_all(self) -> list[NodeInfo]:
        out = []
        for v in self._nodes.values():
            try:
                out.append(NodeInfo.from_json(v))
            except Exception:
                pass
        return out

    async def get_node(self, node_id: str) -> NodeInfo | None:
        raw = self._nodes.get(node_id)
        if not raw:
            return None
        try:
            return NodeInfo.from_json(raw)
        except Exception:
            return None

    async def get_controllers(self) -> list[NodeInfo]:
        all_nodes = await self.get_all()
        return [n for n in all_nodes if n.role in (NodeRole.CONTROLLER, NodeRole.HYBRID)]

    async def get_workers(self) -> list[NodeInfo]:
        all_nodes = await self.get_all()
        return [n for n in all_nodes if n.role in (NodeRole.WORKER, NodeRole.HYBRID)]

    async def is_healthy(self) -> bool:
        return len(await self.get_controllers()) >= 1


class LocalLeaderElector:
    """Single-node: first campaigner wins; no Redis."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._leader: str | None = None

    async def campaign(self, node_id: str) -> bool:
        if self._leader is None:
            self._leader = node_id
            return True
        return self._leader == node_id

    async def refresh(self, node_id: str) -> bool:
        return self._leader == node_id

    async def get_leader(self) -> str | None:
        return self._leader

    async def abdicate(self, node_id: str) -> None:
        if self._leader == node_id:
            self._leader = None

    async def watch(
        self,
        node_id: str,
        on_elected: object,
        on_lost: object,
    ) -> None:
        won = await self.campaign(node_id)
        if won:
            await on_elected()
        while True:
            # Short sleep so dispatch_loop and worker get CPU in single-node
            await asyncio.sleep(0.5)
            if not await self.refresh(node_id):
                await on_lost()
                break
