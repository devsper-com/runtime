"""
memory_utils.py — Workflow hub memory backed by Postgres + pgvector.

The PyPI `vektori` package (0.1.x) is an HTTP client only; it does not embed in-process.
This module writes to Goose migration tables (`vektori_facts`, etc.) using OpenAI
text-embedding-3-small (1536 dims) to match the `vector(1536)` column.

Requires: DATABASE_URL, and either OPENAI_API_KEY or VEKTORI_USE_MOCK_EMBEDDINGS=1 (1536 zero
vectors — dev/CI only; not for production).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------


def workflow_entity_namespace(workflow_id: str, entity_key: str) -> str:
    """
    Vektori user_id encoding the platform's multi-tenant hierarchy.
    Each (workflow, entity) pair gets an isolated memory silo.
    e.g. "workflow:wf-abc123:entity:acme-corp"
    """
    return f"workflow:{workflow_id}:entity:{entity_key}"


def run_session_id(run_id: str) -> str:
    """Each run is a session id string stored on fact rows."""
    return f"run:{run_id}"


# ---------------------------------------------------------------------------
# OpenAI embeddings (1536-dim for vektori_facts.embedding)
# ---------------------------------------------------------------------------


def _openai_embed_sync(text: str) -> list[float]:
    if os.environ.get("VEKTORI_USE_MOCK_EMBEDDINGS", "").strip() == "1":
        return [0.0] * 1536
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for workflow memory (pgvector facts use 1536-dim embeddings), "
            "or set VEKTORI_USE_MOCK_EMBEDDINGS=1 for local smoke tests only."
        )
    payload = {"model": "text-embedding-3-small", "input": (text or "")[:8000]}
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
    return data["data"][0]["embedding"]


# ---------------------------------------------------------------------------
# Minimal result shapes (match attributes used by inject/search helpers)
# ---------------------------------------------------------------------------


class _MemHit:
    __slots__ = ("text", "score", "insights", "sentences")

    def __init__(self, text: str, score: float | None = None):
        self.text = text
        self.score = score
        self.insights: list[Any] = []
        self.sentences: list[Any] = []


class _AddResult:
    __slots__ = ("facts_written",)

    def __init__(self, n: int):
        self.facts_written = n


# ---------------------------------------------------------------------------
# Postgres + pgvector backend
# ---------------------------------------------------------------------------


class _PgVectorMemory:
    """Async facade; blocking IO runs in asyncio.to_thread."""

    def __init__(self, dsn: str):
        self._dsn = dsn

    async def close(self) -> None:
        return None

    def _connect(self):
        from psycopg import connect
        from psycopg.rows import dict_row
        from pgvector.psycopg import register_vector

        conn = connect(self._dsn, autocommit=False, row_factory=dict_row)
        register_vector(conn)
        return conn

    def _sync_add(
        self,
        messages: list[dict],
        user_id: str,
        session_id: str,
    ) -> int:
        parts = []
        for m in messages:
            c = (m.get("content") or "").strip()
            if c:
                role = (m.get("role") or "user").strip()
                parts.append(f"{role}: {c}")
        text = "\n".join(parts)[:12000]
        if not text.strip():
            return 0
        emb = _openai_embed_sync(text)
        rid = session_id if session_id.startswith("run:") else None
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO vektori_facts (id, user_id, text, embedding, source_run_id)
                    VALUES (gen_random_uuid(), %s, %s, %s, %s)
                    """,
                    (user_id, text, emb, rid),
                )
            conn.commit()
        return 1

    async def add(
        self,
        messages: list[dict],
        user_id: str,
        session_id: str,
    ) -> _AddResult:
        n = await asyncio.to_thread(self._sync_add, messages, user_id, session_id)
        return _AddResult(n)

    def _sync_search(self, query: str, user_id: str, limit: int) -> list[_MemHit]:
        q = (query or "").strip()
        if not q:
            return []
        emb = _openai_embed_sync(q)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT text, (embedding <=> %s::vector) AS dist
                    FROM vektori_facts
                    WHERE user_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (emb, user_id, emb, limit),
                )
                rows = cur.fetchall()
        out: list[_MemHit] = []
        for row in rows:
            dist = float(row["dist"]) if row.get("dist") is not None else None
            out.append(_MemHit(str(row["text"]), score=dist))
        return out

    async def search(self, query: str, user_id: str, depth: str = "l1") -> list[_MemHit]:
        _ = depth
        return await asyncio.to_thread(self._sync_search, query, user_id, 24)


_vektori: _PgVectorMemory | None = None
_vektori_lock: asyncio.Lock | None = None


def _get_vektori_lock() -> asyncio.Lock:
    """Return the module-level lock, creating it lazily on the running event loop."""
    global _vektori_lock
    if _vektori_lock is None:
        _vektori_lock = asyncio.Lock()
    return _vektori_lock


async def get_vektori() -> _PgVectorMemory:
    global _vektori
    if _vektori is not None:
        return _vektori
    async with _get_vektori_lock():
        if _vektori is not None:  # double-checked inside lock
            return _vektori
        db_url = (os.environ.get("DATABASE_URL") or "").strip()
        if not db_url:
            raise RuntimeError("DATABASE_URL is required for workflow memory")
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            if os.environ.get("VEKTORI_USE_MOCK_EMBEDDINGS", "").strip() != "1":
                raise RuntimeError(
                    "OPENAI_API_KEY is required for workflow memory (pgvector embeddings use text-embedding-3-small), "
                    "or set VEKTORI_USE_MOCK_EMBEDDINGS=1 for local smoke tests only."
                )
        _vektori = _PgVectorMemory(db_url)
        log.info("workflow_memory_initialized backend=pgvector")
        return _vektori


async def close_vektori() -> None:
    global _vektori, _vektori_lock
    if _vektori is not None:
        async with _get_vektori_lock():
            if _vektori is not None:
                await _vektori.close()
                _vektori = None
                _vektori_lock = None
                log.info("workflow_memory_closed")


# ---------------------------------------------------------------------------
# Core operations (async)
# ---------------------------------------------------------------------------


async def inject_memory_context(
    workflow_id: str,
    entity_key: str,
    task_description: str,
    depth: str = "l1",
) -> str:
    """
    Retrieve relevant memory and return a string for {{memory}} prompt injection.
    Returns "" on any error — memory failure must never block a run.
    """
    try:
        v = await get_vektori()
        results = await v.search(
            query=task_description,
            user_id=workflow_entity_namespace(workflow_id, entity_key),
            depth=depth,
        )
    except Exception as exc:
        log.warning(
            "memory_inject_failed workflow_id=%s entity_key=%s error=%s",
            workflow_id,
            entity_key,
            exc,
        )
        return ""

    if not results:
        return ""

    lines = ["## Memory Context (from previous runs on this entity)\n"]
    for r in results:
        lines.append(f"- {r.text}")
        if hasattr(r, "insights") and r.insights:
            for insight in r.insights:
                lines.append(f"  → [pattern] {insight.text}")
        if hasattr(r, "sentences") and r.sentences:
            for sentence in r.sentences[:2]:
                lines.append(f"  > {sentence.text}")

    return "\n".join(lines)


async def persist_run_memory(
    workflow_id: str,
    entity_key: str,
    run_id: str,
    agent_messages: list[dict],
) -> int:
    """Persist agent messages as a fact row after a run."""
    if not agent_messages:
        return 0

    try:
        v = await get_vektori()
        result = await v.add(
            messages=agent_messages,
            user_id=workflow_entity_namespace(workflow_id, entity_key),
            session_id=run_session_id(run_id),
        )
        facts_written = int(getattr(result, "facts_written", 0))
        log.info("memory_persisted run_id=%s facts=%s", run_id, facts_written)
        return facts_written
    except Exception as exc:
        log.error("memory_persist_failed run_id=%s error=%s", run_id, exc)
        return 0


async def search_memory(
    workflow_id: str,
    entity_key: str,
    query: str,
    depth: str = "l1",
) -> list[dict]:
    """For the internal memory browser API endpoint."""
    v = await get_vektori()
    results = await v.search(
        query=query,
        user_id=workflow_entity_namespace(workflow_id, entity_key),
        depth=depth,
    )
    output: list[dict] = []
    for r in results:
        item: dict[str, Any] = {"text": r.text, "score": getattr(r, "score", None)}
        if hasattr(r, "insights") and r.insights:
            item["insights"] = [{"text": i.text} for i in r.insights]
        if hasattr(r, "sentences") and r.sentences:
            item["sentences"] = [
                {"text": s.text, "role": getattr(s, "role", "")}
                for s in r.sentences
            ]
        output.append(item)
    return output


async def add_memory_manually(
    workflow_id: str,
    entity_key: str,
    messages: list[dict],
    session_id: str | None = None,
) -> None:
    """For the 'add memory' button in the UI."""
    v = await get_vektori()
    await v.add(
        messages=messages,
        user_id=workflow_entity_namespace(workflow_id, entity_key),
        session_id=session_id or f"manual:{uuid.uuid4()}",
    )


# ---------------------------------------------------------------------------
# Sync bridges (FastAPI sync handlers / swarmworker thread)
# ---------------------------------------------------------------------------


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    return asyncio.run(coro)


def format_workflow_memory_context(
    workflow_id: str,
    entity_key: str,
    task_description: str,
    depth: str = "l1",
    top_k: int = 10,
) -> str:
    _ = top_k
    return _run_async(
        inject_memory_context(
            workflow_id=workflow_id,
            entity_key=entity_key,
            task_description=task_description,
            depth=depth,
        )
    )


def persist_workflow_run_memory(
    workflow_id: str,
    entity_key: str,
    run_id: str,
    agent_messages: list[dict],
) -> int:
    return _run_async(persist_run_memory(workflow_id, entity_key, run_id, agent_messages))


def search_workflow_memory(
    workflow_id: str,
    entity_key: str,
    query: str,
    depth: str = "l1",
    limit: int = 20,
) -> list[dict]:
    _ = limit
    return _run_async(search_memory(workflow_id, entity_key, query, depth))


def add_memory_manually_sync(
    workflow_id: str,
    entity_key: str,
    messages: list[dict],
    session_id: str | None = None,
) -> int:
    _run_async(
        add_memory_manually(
            workflow_id=workflow_id,
            entity_key=entity_key,
            messages=messages,
            session_id=session_id,
        )
    )
    return len(messages)


def update_namespace_stats(workflow_template_id: str, entity_key: str, run_id: str) -> None:
    """Update platform namespace fact counters using vektori_facts rows."""
    dsn = (os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        return

    from psycopg import connect
    from psycopg.rows import dict_row

    user_ns = workflow_entity_namespace(workflow_template_id, entity_key)

    with connect(dsn, row_factory=dict_row, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*)::bigint AS c FROM vektori_facts WHERE user_id = %s",
                (user_ns,),
            )
            cnt = int(cur.fetchone()["c"])
            rid = None
            try:
                rid = uuid.UUID(run_id)
            except Exception:
                pass
            cur.execute(
                """
                UPDATE workflow_memory_namespaces
                SET fact_count = %s, last_run_id = %s, updated_at = now()
                WHERE workflow_template_id = %s::uuid AND entity_key = %s
                """,
                (cnt, rid, workflow_template_id, entity_key),
            )
        conn.commit()


def apply_prompt_template(template: str, inputs: dict[str, Any], memory_ctx: str) -> str:
    """Replace {{memory}} and other {{variable}} placeholders."""
    out = (template or "").replace("{{memory}}", memory_ctx or "")
    for key, val in (inputs or {}).items():
        ph = "{{" + key + "}}"
        if ph not in out:
            continue
        if isinstance(val, (dict, list)):
            rep = json.dumps(val, ensure_ascii=False)
        else:
            rep = str(val)
        out = out.replace(ph, rep)
    return out


def messages_from_swarm_result(task: str, results: dict | None) -> list[dict[str, Any]]:
    """Best-effort message list for Vektori persistence when no raw history exists."""
    msgs: list[dict[str, Any]] = [{"role": "user", "content": task or ""}]
    if results:
        parts = []
        for k, v in results.items():
            parts.append(f"{k}: {v}")
        body = "\n".join(parts)[:12000]
        if body.strip():
            msgs.append({"role": "assistant", "content": body})
    return msgs
