"""
Platform-backed memory adapter for org-scoped memory cloud.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from devsper.memory.memory_types import MemoryRecord, MemoryType


class PlatformMemoryStore:
    def __init__(self, base_url: str | None = None, org_slug: str | None = None, token: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("DEVSPER_PLATFORM_API_URL", "")).rstrip("/")
        self.org_slug = org_slug or os.environ.get("DEVSPER_PLATFORM_ORG", "")
        self.token = token or os.environ.get("DEVSPER_PLATFORM_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _enabled(self) -> bool:
        return bool(self.base_url and self.org_slug)

    def store(self, record: MemoryRecord, namespace: str | None = None) -> str:
        if not self._enabled():
            return record.id
        payload = {
            "content": record.content,
            "tags": record.tags,
            "namespace": namespace or "",
            "metadata": {"memory_type": record.memory_type.value, "source_task": record.source_task},
        }
        resp = requests.post(self._url(f"/orgs/{self.org_slug}/memory"), json=payload, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("id") or record.id)

    def list_memory(self, limit: int = 100, namespace: str | None = None, **_: Any) -> list[MemoryRecord]:
        if not self._enabled():
            return []
        url = self._url(f"/orgs/{self.org_slug}/memory")
        resp = requests.get(url, headers=self._headers(), timeout=15)
        resp.raise_for_status()
        items = (resp.json() or {}).get("memories", [])[:limit]
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
        if not self._enabled():
            return []
        params = {"q": query, "mode": mode}
        if namespace:
            params["namespace"] = namespace
        resp = requests.get(
            self._url(f"/orgs/{self.org_slug}/memory/search"),
            params=params,
            headers=self._headers(),
            timeout=15,
        )
        resp.raise_for_status()
        rows = (resp.json() or {}).get("results", [])[:limit]
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
