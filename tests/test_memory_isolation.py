"""Storage-layer isolation for namespaced memory (project/org/run scopes)."""

from __future__ import annotations

import tempfile

import pytest

from devsper.agents.agent import Agent
from devsper.memory.memory_router import MemoryRouter
from devsper.memory.memory_store import MemoryStore, generate_memory_id
from devsper.memory.memory_types import MemoryRecord, MemoryType


@pytest.fixture()
def sqlite_store() -> MemoryStore:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    return MemoryStore(db_path=path)


class TestNamespaceIsolation_WritesDoNotCross:
    def test_writes_do_not_cross(self, sqlite_store: MemoryStore) -> None:
        ns_a = "project:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        ns_b = "project:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        rid = generate_memory_id()
        sqlite_store.store(
            MemoryRecord(
                id=rid,
                memory_type=MemoryType.SEMANTIC,
                content="secret-a",
                tags=["t"],
            ),
            namespace=ns_a,
        )
        sqlite_store.store(
            MemoryRecord(
                id=generate_memory_id(),
                memory_type=MemoryType.SEMANTIC,
                content="secret-b",
                tags=["t"],
            ),
            namespace=ns_b,
        )
        la = sqlite_store.list_memory(namespace=ns_a)
        lb = sqlite_store.list_memory(namespace=ns_b)
        assert len(la) == 1 and la[0].content == "secret-a"
        assert len(lb) == 1 and lb[0].content == "secret-b"
        assert sqlite_store.retrieve(rid, namespace=ns_b) is None
        assert sqlite_store.retrieve(rid, namespace=ns_a) is not None


class TestNamespaceIsolation_PurgeRemovesOnlyTarget:
    def test_purge(self, sqlite_store: MemoryStore) -> None:
        na = "project:p1"
        nb = "project:p2"
        sqlite_store.store(
            MemoryRecord(
                id=generate_memory_id(),
                memory_type=MemoryType.SEMANTIC,
                content="x",
            ),
            namespace=na,
        )
        sqlite_store.store(
            MemoryRecord(
                id=generate_memory_id(),
                memory_type=MemoryType.SEMANTIC,
                content="y",
            ),
            namespace=nb,
        )
        sqlite_store.purge_namespace(na)
        assert len(sqlite_store.list_memory(namespace=na)) == 0
        assert len(sqlite_store.list_memory(namespace=nb)) == 1


class TestNamespaceNone_BackwardCompatible:
    def test_default_namespace_empty(self, sqlite_store: MemoryStore) -> None:
        mid = generate_memory_id()
        sqlite_store.store(
            MemoryRecord(
                id=mid,
                memory_type=MemoryType.SEMANTIC,
                content="legacy",
            ),
            namespace=None,
        )
        rows = sqlite_store.list_memory(namespace=None)
        assert len(rows) == 1
        assert sqlite_store.retrieve(mid, namespace=None).content == "legacy"


class TestProjectMemory_AgentsShareWithinProject:
    def test_shared_context(self, sqlite_store: MemoryStore) -> None:
        ns = "project:shared-proj"
        router = MemoryRouter(store=sqlite_store, default_namespace=ns)
        Agent(memory_router=router, memory_namespace=ns, store_result_to_memory=True)
        a2 = Agent(memory_router=router, memory_namespace=ns, store_result_to_memory=False)
        sqlite_store.store(
            MemoryRecord(
                id=generate_memory_id(),
                memory_type=MemoryType.SEMANTIC,
                content="from-agent-context",
                tags=["user_injection"],
            ),
            namespace=ns,
        )
        ctx = a2.memory_router.get_memory_context("d1")
        assert "from-agent-context" in ctx


class TestProjectMemory_AgentsIsolatedAcrossProjects:
    def test_no_leak(self, sqlite_store: MemoryStore) -> None:
        ns1 = "project:p-one"
        ns2 = "project:p-two"
        sqlite_store.store(
            MemoryRecord(
                id=generate_memory_id(),
                memory_type=MemoryType.SEMANTIC,
                content="only-p1",
                tags=["user_injection"],
            ),
            namespace=ns1,
        )
        r2 = MemoryRouter(store=sqlite_store, default_namespace=ns2)
        a = Agent(memory_router=r2, memory_namespace=ns2)
        ctx = a.memory_router.get_memory_context("q")
        assert "only-p1" not in ctx
