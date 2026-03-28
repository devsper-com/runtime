import asyncio

from devsper.pool.org_pool import OrgPoolManager
from tests.pool.fixtures import make_pool


class NodeProvStub:
    def __init__(self):
        self.calls = []
        self._n = 0

    async def provision(self, *, org_id: str, user_id: str, node_type: str, dedicated: bool):
        self.calls.append((org_id, user_id, node_type, dedicated))
        self._n += 1
        return {"node_id": f"node-{self._n}"}


def test_org_pool_manager_provisions_nodes():
    async def run():
        pool = await make_pool()
        npc = NodeProvStub()
        opm = OrgPoolManager(pool, npc)
        node = await opm.provision_dedicated_node("org", "u", workers_per_node=4)
        assert node.node_id == "node-1"
        nodes = await opm.add_to_org_pool("org", "u", count=2)
        assert nodes == ["node-2", "node-3"]

    asyncio.run(run())

