"""
Platform-backed memory adapter for org-scoped memory cloud.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from devsper.memory.memory_types import MemoryRecord, MemoryType
from devsper.platform.request_builder import PlatformAPIError, PlatformAPIRequestBuilder


class PlatformMemoryStore:
    def __init__(self, base_url: str | None = None, org_slug: str | None = None, token: str | None = None) -> None:
        self.api = PlatformAPIRequestBuilder(base_url=base_url, org_slug=org_slug, token=token)

    def store(self, record: MemoryRecord, namespace: str | None = None) -> str:
        if not self.api.enabled():
            return record.id
        payload = {
            "content": record.content,
            "tags": record.tags,
            "namespace": namespace or "",
            "metadata": {"memory_type": record.memory_type.value, "source_task": record.source_task},
        }
        try:
            data = self.api.post_json(
                f"/orgs/{self.api.org_slug}/memory",
                json_body=payload,
            )
        except PlatformAPIError:
            # Best-effort: memory writes should not kill task execution.
            return record.id
        return str((data or {}).get("id") or record.id)

    def list_memory(self, limit: int = 100, namespace: str | None = None, **_: Any) -> list[MemoryRecord]:
        if not self.api.enabled():
            return []
        try:
            items = (self.api.get_json(f"/orgs/{self.api.org_slug}/memory") or {}).get("memories", [])[:limit]
        except PlatformAPIError:
            return []
        out: list[MemoryRecord] = []
        for x in items:
            meta = x.get("metadata") or {}
            mt = str(meta.get("memory_type") or "semantic")
            try:
                mtype = MemoryType(mt)
            except Exception:
                mtype = MemoryType.SEMANTIC
            ts = x.get("created_at")
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if ts else datetime.now(timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)
            out.append(
                MemoryRecord(
                    id=str(x.get("id", "")),
                    memory_type=mtype,
                    content=str(x.get("content", "")),
                    tags=list(x.get("tags") or []),
                    timestamp=dt,
                    source_task=str(meta.get("source_task") or ""),
                )
            )
        if namespace:
            out = [m for m in out if namespace == "" or namespace in (m.source_task or namespace)]
        return out

    def search(self, query: str, namespace: str | None = None, mode: str = "semantic", limit: int = 20) -> list[MemoryRecord]:
        if not self.api.enabled():
            return []
        params = {"q": query, "mode": mode}
        if namespace:
            params["namespace"] = namespace
        try:
            rows = (self.api.get_json(f"/orgs/{self.api.org_slug}/memory/search", params=params) or {}).get("results", [])[:limit]
        except PlatformAPIError:
            return []
        out: list[MemoryRecord] = []
        for x in rows:
            meta = x.get("metadata") or {}
            out.append(
                MemoryRecord(
                    id=str(x.get("id", "")),
                    memory_type=MemoryType.SEMANTIC,
                    content=str(x.get("content", "")),
                    tags=list(x.get("tags") or []),
                    timestamp=datetime.now(timezone.utc),
                    source_task=str(meta.get("source_task") or ""),
                )
            )
        return out
