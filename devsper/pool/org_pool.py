from __future__ import annotations

from .models import NodeRecord, PoolTier


class OrgPoolManager:
    def __init__(self, pool, node_provisioner_client):
        self.pool = pool
        self.npc = node_provisioner_client

    async def provision_dedicated_node(self, org_id: str, user_id: str, workers_per_node: int = 4) -> NodeRecord:
        assert 4 <= workers_per_node <= 5, "Dedicated nodes run 4-5 workers"
        node_info = await self.npc.provision(org_id=org_id, user_id=user_id, node_type="large", dedicated=True)
        node = NodeRecord(
            node_id=node_info["node_id"],
            org_id=org_id,
            tier=PoolTier.DEDICATED,
            max_workers=workers_per_node,
            profile=getattr(self.pool.config, "profile", "prod"),
        )
        await self.pool.store.save_node(node)
        return node

    async def add_to_org_pool(self, org_id: str, user_id: str, count: int = 2) -> list[str]:
        node_ids: list[str] = []
        for _ in range(count):
            node_info = await self.npc.provision(org_id=org_id, user_id=user_id, node_type="standard", dedicated=False)
            node = NodeRecord(
                node_id=node_info["node_id"],
                org_id=org_id,
                tier=PoolTier.ORG,
                max_workers=4,
                profile=getattr(self.pool.config, "profile", "prod"),
            )
            await self.pool.store.save_node(node)
            node_ids.append(node.node_id)
        return node_ids

