"""
Redis-backed MemoryStore for distributed mode.

Implements the same *sync* interface as MemoryStore (store/retrieve/list_memory),
so it can be used by MemoryRouter/MemoryIndex without refactors.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from devsper.memory.memory_store import MemoryStore, _row_to_record
from devsper.memory.memory_types import MemoryRecord, MemoryType


class RedisMemoryStore(MemoryStore):
    """
    Shared memory store backed by Redis hashes + sorted set.

    Keys (namespace None → same as legacy run-scoped layout):
      devsper:memory:{run_id}:records  (HASH) memory_id -> json row
      devsper:memory:{run_id}:index    (ZSET) memory_id -> timestamp score

    With explicit namespace (e.g. project:uuid):
      devsper:memory:{namespace}:records / :index
    """

    def __init__(self, redis_url: str, run_id: str, default_namespace: str | None = None):
        # Don't init sqlite schema; this store isn't sqlite-backed.
        self.db_path = ""
        try:
            import redis
        except Exception as e:
            raise ImportError("RedisMemoryStore requires 'redis' package.") from e
        self._redis = redis.Redis.from_url(redis_url, decode_responses=True)
        self._run_id = run_id
        self._default_namespace = default_namespace

    def set_default_namespace(self, namespace: str | None) -> None:
        """Switch logical partition for subsequent ops with namespace=None."""
        self._default_namespace = namespace

    def _keys(self, namespace: str | None) -> tuple[str, str]:
        ns = namespace if namespace is not None else self._default_namespace
        if ns is None or ns == "":
            base = f"devsper:memory:{self._run_id}"
        else:
            base = f"devsper:memory:{ns}"
        return f"{base}:records", f"{base}:index"

    def store(self, record: MemoryRecord, namespace: str | None = None) -> str:
        records_key, index_key = self._keys(namespace)
        row = record.to_store_row()
        row["run_id"] = record.run_id or self._run_id
        # embedding can be list[float] or None
        data = json.dumps(row)
        memory_id = row["memory_id"]
        score = time.time()
        pipe = self._redis.pipeline()
        pipe.hset(records_key, memory_id, data)
        pipe.zadd(index_key, {memory_id: score})
        pipe.expire(records_key, 86400 * 7)
        pipe.expire(index_key, 86400 * 7)
        pipe.execute()
        return memory_id

    def retrieve(self, memory_id: str, namespace: str | None = None) -> MemoryRecord | None:
        records_key, _ = self._keys(namespace)
        raw = self._redis.hget(records_key, memory_id)
        if not raw:
            return None
        try:
            row = json.loads(raw)
            return _row_to_record(row)
        except Exception:
            return None

    def delete(self, memory_id: str, namespace: str | None = None) -> bool:
        records_key, index_key = self._keys(namespace)
        pipe = self._redis.pipeline()
        pipe.hdel(records_key, memory_id)
        pipe.zrem(index_key, memory_id)
        res = pipe.execute()
        try:
            return bool(res and res[0] > 0)
        except Exception:
            return False

    def list_memory(
        self,
        memory_type: MemoryType | None = None,
        limit: int = 100,
        offset: int = 0,
        tag_contains: str | None = None,
        include_archived: bool = False,
        run_id_filter: str | None = None,
        namespace: str | None = None,
    ) -> list[MemoryRecord]:
        _, index_key = self._keys(namespace)
        records_key, _ = self._keys(namespace)
        ids = self._redis.zrevrange(index_key, 0, -1)
        if not ids:
            return []
        out: list[MemoryRecord] = []
        for mid in ids:
            raw = self._redis.hget(records_key, mid)
            if not raw:
                continue
            try:
                row = json.loads(raw)
                rec = _row_to_record(row)
            except Exception:
                continue
            if run_id_filter is not None and (rec.run_id or "") != run_id_filter:
                continue
            if memory_type is not None and rec.memory_type != memory_type:
                continue
            if not include_archived and getattr(rec, "archived", False):
                continue
            if tag_contains:
                if not any(tag_contains in t for t in (rec.tags or [])):
                    continue
            out.append(rec)
        return out[offset : offset + limit]

    def list_all_ids(self, memory_type: MemoryType | None = None, namespace: str | None = None) -> list[str]:
        _, index_key = self._keys(namespace)
        records_key, _ = self._keys(namespace)
        ids = self._redis.zrevrange(index_key, 0, -1)
        if not ids:
            return []
        if memory_type is None:
            return [str(i) for i in ids]
        out: list[str] = []
        for mid in ids:
            raw = self._redis.hget(records_key, mid)
            if not raw:
                continue
            try:
                row = json.loads(raw)
                rec = _row_to_record(row)
                if rec.memory_type == memory_type:
                    out.append(str(mid))
            except Exception:
                continue
        return out

    def set_archived(self, memory_id: str, archived: bool = True, namespace: str | None = None) -> bool:
        rec = self.retrieve(memory_id, namespace=namespace)
        if rec is None:
            return False
        rec = rec.model_copy(update={"archived": archived})
        self.store(rec, namespace=namespace)
        return True

    def purge_namespace(self, namespace: str) -> None:
        if not namespace or not str(namespace).strip():
            return
        records_key, index_key = self._keys(namespace)
        pipe = self._redis.pipeline()
        pipe.delete(records_key)
        pipe.delete(index_key)
        pipe.execute()

