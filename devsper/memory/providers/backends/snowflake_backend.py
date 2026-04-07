"""
SnowflakeBackend: Snowflake-backed memory store using VECTOR(FLOAT, 1536) columns.

Credential resolution order (never stored in config files):
  1. devsper credential store: devsper credentials set snowflake password
  2. SNOWFLAKE_PASSWORD environment variable
  3. Raises ValueError with a helpful message if neither is set.

Non-secret fields (account, user, database, schema, warehouse, role) can be set
in [memory.snowflake] TOML, overridden by SNOWFLAKE_* env vars.

Requires: devsper[snowflake] extra (snowflake-connector-python>=3.6.0)
          OPENAI_API_KEY for 1536-dim embeddings (or VEKTORI_USE_MOCK_EMBEDDINGS=1 for dev)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from devsper.memory.providers.base import MemoryBackend, MemoryQuery

if TYPE_CHECKING:
    from devsper.memory.memory_types import MemoryRecord, MemoryType

log = logging.getLogger(__name__)

_EMBED_DIM = 1536


def _resolve_password() -> str:
    """Resolve Snowflake password from credential store or env. Never from config."""
    from devsper.credentials import get_credential

    pw = get_credential("snowflake", "password") or os.environ.get("SNOWFLAKE_PASSWORD", "")
    if not pw:
        raise ValueError(
            "Snowflake password not found. Store it securely with:\n"
            "  devsper credentials set snowflake password\n"
            "Or set the SNOWFLAKE_PASSWORD environment variable."
        )
    return pw


def _resolve_field(key: str, env_var: str, toml_value: str) -> str:
    """Resolve a non-secret Snowflake field: credential store → env var → TOML value."""
    from devsper.credentials import get_credential

    return (
        get_credential("snowflake", key)
        or os.environ.get(env_var, "")
        or toml_value
    )


def _vector_literal(embedding: list[float]) -> str:
    """Format a float list as a Snowflake array literal ready to cast to VECTOR.
    Output: [0.0,0.0,...] (unquoted array literal — Snowflake VECTOR syntax, not a string).
    Safe to inline — values are always floats produced by _embed_sync, never user input.
    """
    return "[" + ",".join(str(v) for v in embedding) + "]"


def _embed_sync(text: str) -> list[float]:
    """Produce a 1536-dim embedding for Snowflake VECTOR column."""
    if os.environ.get("VEKTORI_USE_MOCK_EMBEDDINGS", "").strip() == "1":
        return [0.0] * _EMBED_DIM

    import httpx

    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for Snowflake memory embeddings "
            "(uses text-embedding-3-small / 1536 dims). "
            "Set VEKTORI_USE_MOCK_EMBEDDINGS=1 for local dev only."
        )
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "text-embedding-3-small", "input": (text or "")[:8000]},
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]


def _row_to_record(row: dict) -> "MemoryRecord":
    from devsper.memory.memory_types import MemoryRecord, MemoryType

    tags_raw = row.get("TAGS") or row.get("tags") or ""
    if not tags_raw:
        tags = []
    else:
        try:
            parsed = json.loads(tags_raw)
            # json.loads can return a string (if stored as JSON string) or list
            tags = parsed if isinstance(parsed, list) else [str(parsed)]
        except Exception:
            # Stored as comma-separated plain text (to_store_row() format)
            tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()]

    emb_raw = row.get("EMBEDDING") or row.get("embedding")
    embedding: list[float] | None = None
    if emb_raw is not None:
        if isinstance(emb_raw, (list, tuple)):
            embedding = list(emb_raw)
        else:
            try:
                embedding = json.loads(str(emb_raw))
            except Exception:
                embedding = None

    ts_raw = row.get("TIMESTAMP") or row.get("timestamp")
    if isinstance(ts_raw, datetime):
        ts = ts_raw
    else:
        try:
            ts = datetime.fromisoformat(str(ts_raw))
        except Exception:
            ts = datetime.now(timezone.utc)

    mem_type_raw = row.get("MEMORY_TYPE") or row.get("memory_type") or "episodic"
    try:
        mem_type = MemoryType(mem_type_raw)
    except ValueError:
        mem_type = MemoryType.EPISODIC

    return MemoryRecord(
        id=str(row.get("MEMORY_ID") or row.get("memory_id") or ""),
        memory_type=mem_type,
        content=str(row.get("CONTENT") or row.get("content") or ""),
        tags=tags,
        timestamp=ts,
        source_task=str(row.get("SOURCE_TASK") or row.get("source_task") or ""),
        embedding=embedding,
        run_id=str(row.get("RUN_ID") or row.get("run_id") or ""),
        archived=bool(row.get("ARCHIVED") or row.get("archived") or False),
    )


class SnowflakeBackend(MemoryBackend):
    """
    Snowflake-backed memory store.

    Uses VECTOR(FLOAT, 1536) columns and VECTOR_COSINE_SIMILARITY for native
    semantic search. All credentials resolved via the devsper credential store
    or environment variables — never from constructor arguments.
    """

    def __init__(
        self,
        account: str = "",
        user: str = "",
        database: str = "",
        schema: str = "",
        warehouse: str = "",
        role: str = "",
        table: str = "devsper_memory",
    ) -> None:
        # Resolve all connection params — credentials from store/env, non-secrets allow TOML fallback
        self._account = _resolve_field("account", "SNOWFLAKE_ACCOUNT", account)
        self._user = _resolve_field("user", "SNOWFLAKE_USER", user)
        self._password = _resolve_password()
        self._database = _resolve_field("database", "SNOWFLAKE_DATABASE", database)
        self._schema = _resolve_field("schema", "SNOWFLAKE_SCHEMA", schema)
        self._warehouse = _resolve_field("warehouse", "SNOWFLAKE_WAREHOUSE", warehouse)
        self._role = _resolve_field("role", "SNOWFLAKE_ROLE", role)
        self._table = table
        self._init_schema_sync()

    @property
    def name(self) -> str:
        return "snowflake"

    @property
    def supports_native_vector_search(self) -> bool:
        return True

    def _connect(self):
        try:
            import snowflake.connector
        except ImportError as e:
            raise ImportError(
                "Snowflake memory backend requires 'snowflake-connector-python'. "
                "Install with: pip install 'devsper[snowflake]'"
            ) from e

        params: dict[str, Any] = {
            "account": self._account,
            "user": self._user,
            "password": self._password,
            "database": self._database,
            "schema": self._schema,
            "warehouse": self._warehouse,
        }
        if self._role:
            params["role"] = self._role
        return snowflake.connector.connect(**params)

    def _init_schema_sync(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._table} (
                        memory_id     VARCHAR(36)    NOT NULL PRIMARY KEY,
                        memory_type   VARCHAR(32)    NOT NULL,
                        content       TEXT           NOT NULL,
                        tags          VARCHAR(4096)  DEFAULT '',
                        timestamp     TIMESTAMP_TZ   NOT NULL,
                        source_task   VARCHAR(1024)  DEFAULT '',
                        embedding     VECTOR(FLOAT, {_EMBED_DIM}),
                        run_id        VARCHAR(128)   DEFAULT '',
                        archived      BOOLEAN        DEFAULT FALSE,
                        namespace     VARCHAR(512)   DEFAULT ''
                    )
                """)
                # Clustering replaces indexes in Snowflake
                try:
                    cur.execute(f"""
                        ALTER TABLE {self._table}
                        CLUSTER BY (namespace, memory_type)
                    """)
                except Exception:
                    pass  # Already clustered or not supported in this edition

    def _sync_store(self, record: "MemoryRecord", namespace: str) -> str:
        import snowflake.connector

        row = record.to_store_row()
        memory_id = row["memory_id"]
        ns = namespace or ""

        # Compute embedding — formatted as a SQL literal (safe: always floats from embed fn)
        emb_literal: str | None = None
        try:
            emb = _embed_sync(record.content)
            emb_literal = _vector_literal(emb)
        except Exception as e:
            log.warning("snowflake_memory embed_failed memory_id=%s error=%s", memory_id, e)

        # to_store_row() already returns tags as a comma-separated string; store as-is
        tags_str = row.get("tags") or ""
        ts = row.get("timestamp") or datetime.now(timezone.utc).isoformat()
        archived = bool(row.get("archived", False))
        source_task = row.get("source_task", "") or ""
        run_id = row.get("run_id", "") or ""

        # Inline the vector literal directly — bypasses connector quoting issues.
        # Safe: emb_literal contains only floats produced by _embed_sync, never user data.
        if emb_literal is not None:
            emb_sql = f"{emb_literal}::VECTOR(FLOAT, {_EMBED_DIM})"
        else:
            emb_sql = "NULL"

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    MERGE INTO {self._table} AS tgt
                    USING (SELECT %s AS mid) AS src ON tgt.memory_id = src.mid
                    WHEN MATCHED THEN UPDATE SET
                        content = %s, memory_type = %s, tags = %s, timestamp = %s,
                        source_task = %s, embedding = {emb_sql}, run_id = %s,
                        archived = %s, namespace = %s
                    WHEN NOT MATCHED THEN INSERT
                        (memory_id, memory_type, content, tags, timestamp,
                         source_task, embedding, run_id, archived, namespace)
                    VALUES (src.mid, %s, %s, %s, %s, %s, {emb_sql}, %s, %s, %s)
                """, (
                    memory_id,
                    # UPDATE params
                    row["content"], row["memory_type"], tags_str, ts,
                    source_task, run_id, archived, ns,
                    # INSERT params (memory_id comes from src.mid)
                    row["memory_type"], row["content"], tags_str, ts,
                    source_task, run_id, archived, ns,
                ))
        return memory_id

    def _sync_retrieve(self, memory_id: str, namespace: str) -> "MemoryRecord | None":
        import snowflake.connector
        ns = namespace or ""
        with self._connect() as conn:
            with conn.cursor(snowflake.connector.DictCursor) as cur:
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE memory_id = %s AND namespace = %s LIMIT 1",
                    (memory_id, ns),
                )
                row = cur.fetchone()
        return _row_to_record(row) if row else None

    def _sync_delete(self, memory_id: str, namespace: str) -> bool:
        ns = namespace or ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {self._table} WHERE memory_id = %s AND namespace = %s",
                    (memory_id, ns),
                )
                return (cur.rowcount or 0) > 0

    def _sync_list_memory(
        self,
        memory_type: "MemoryType | None",
        limit: int,
        offset: int,
        tag_contains: str | None,
        include_archived: bool,
        run_id_filter: str | None,
        namespace: str | None,
    ) -> "list[MemoryRecord]":
        import snowflake.connector

        ns = namespace or ""
        clauses = ["namespace = %s"]
        params: list[Any] = [ns]

        if memory_type is not None:
            clauses.append("memory_type = %s")
            params.append(memory_type.value)
        if not include_archived:
            clauses.append("archived = FALSE")
        if run_id_filter is not None:
            clauses.append("run_id = %s")
            params.append(run_id_filter)
        if tag_contains:
            clauses.append("tags ILIKE %s")
            params.append(f"%{tag_contains}%")

        where = " AND ".join(clauses)
        params.extend([limit, offset])

        with self._connect() as conn:
            with conn.cursor(snowflake.connector.DictCursor) as cur:
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE {where} "
                    f"ORDER BY timestamp DESC LIMIT %s OFFSET %s",
                    params,
                )
                rows = cur.fetchall()
        return [_row_to_record(r) for r in rows]

    def _sync_list_all_ids(
        self,
        memory_type: "MemoryType | None",
        namespace: str | None,
    ) -> list[str]:
        ns = namespace or ""
        clauses = ["namespace = %s"]
        params: list[Any] = [ns]
        if memory_type is not None:
            clauses.append("memory_type = %s")
            params.append(memory_type.value)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT memory_id FROM {self._table} WHERE {where} ORDER BY timestamp DESC",
                    params,
                )
                return [str(r[0]) for r in cur.fetchall()]

    def _sync_query_similar(
        self,
        query: MemoryQuery,
        query_embedding: list[float],
    ) -> "list[MemoryRecord]":
        import snowflake.connector

        ns = query.namespace or ""
        archived_clause = "" if query.include_archived else "AND archived = FALSE"
        # Inline vector literal — safe, values come from _embed_sync (floats only)
        qvec_sql = f"{_vector_literal(query_embedding)}::VECTOR(FLOAT, {_EMBED_DIM})"

        with self._connect() as conn:
            with conn.cursor(snowflake.connector.DictCursor) as cur:
                cur.execute(f"""
                    SELECT *,
                        VECTOR_COSINE_SIMILARITY(embedding, {qvec_sql}) AS similarity_score
                    FROM {self._table}
                    WHERE namespace = %s
                      AND embedding IS NOT NULL
                      {archived_clause}
                      AND VECTOR_COSINE_SIMILARITY(embedding, {qvec_sql}) >= %s
                    ORDER BY similarity_score DESC
                    LIMIT %s
                """, (ns, query.min_similarity, query.top_k))
                rows = cur.fetchall()
        return [_row_to_record(r) for r in rows]

    # -------------------------------------------------------------------------
    # Public async interface
    # -------------------------------------------------------------------------

    async def store(self, record: "MemoryRecord", namespace: str | None = None) -> str:
        return await asyncio.to_thread(self._sync_store, record, namespace or "")

    async def retrieve(self, memory_id: str, namespace: str | None = None) -> "MemoryRecord | None":
        return await asyncio.to_thread(self._sync_retrieve, memory_id, namespace or "")

    async def delete(self, memory_id: str, namespace: str | None = None) -> bool:
        return await asyncio.to_thread(self._sync_delete, memory_id, namespace or "")

    async def list_memory(
        self,
        memory_type: "MemoryType | None" = None,
        limit: int = 100,
        offset: int = 0,
        tag_contains: str | None = None,
        include_archived: bool = False,
        run_id_filter: str | None = None,
        namespace: str | None = None,
    ) -> "list[MemoryRecord]":
        return await asyncio.to_thread(
            self._sync_list_memory,
            memory_type, limit, offset, tag_contains,
            include_archived, run_id_filter, namespace,
        )

    async def list_all_ids(
        self,
        memory_type: "MemoryType | None" = None,
        namespace: str | None = None,
    ) -> list[str]:
        return await asyncio.to_thread(self._sync_list_all_ids, memory_type, namespace)

    async def query_similar(self, query: MemoryQuery) -> "list[MemoryRecord]":
        try:
            query_emb = await asyncio.to_thread(_embed_sync, query.text)
        except Exception as e:
            log.warning("snowflake_memory query_embed_failed error=%s", e)
            return []
        return await asyncio.to_thread(self._sync_query_similar, query, query_emb)

    async def health(self) -> bool:
        def _check() -> bool:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return cur.fetchone() is not None

        try:
            return await asyncio.to_thread(_check)
        except Exception:
            return False
