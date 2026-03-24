"""
Persistent memory store: SQLite-backed store, retrieve, delete, list.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from devsper.memory.memory_types import MemoryRecord, MemoryType


def _default_db_path() -> str:
    from devsper.config import get_config

    base = os.environ.get("DEVSPER_DATA_DIR") or get_config().data_dir
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "memory.db")


def _norm_namespace(namespace: str | None) -> str:
    """SQLite partition key; empty string means legacy default (same as namespace=None)."""
    if namespace is None or namespace == "":
        return ""
    return namespace


class MemoryStore:
    """Local persistent store for memory records. Uses SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or _default_db_path()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    memory_id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tags TEXT,
                    timestamp TEXT NOT NULL,
                    source_task TEXT,
                    embedding TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_memory_type ON memory(memory_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_memory_timestamp ON memory(timestamp)"
            )
            try:
                conn.execute("ALTER TABLE memory ADD COLUMN run_id TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE memory ADD COLUMN archived INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute(
                    "ALTER TABLE memory ADD COLUMN namespace TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_memory_namespace ON memory(namespace)"
            )

    def store(self, record: MemoryRecord, namespace: str | None = None) -> str:
        """Store a memory record. Returns record id. Redacts PII if compliance.pii_redaction enabled."""
        content = record.content
        try:
            from devsper.config import get_config
            cfg = get_config()
            if getattr(getattr(cfg, "compliance", None), "pii_redaction", False):
                from devsper.compliance.pii import PIIRedactor
                redactor = PIIRedactor(
                    pii_types=getattr(cfg.compliance, "pii_types", None),
                    gdpr_mode=getattr(cfg.compliance, "gdpr_mode", False),
                )
                res = redactor.redact(content or "")
                content = res.redacted_text
        except Exception:
            pass
        if content != record.content:
            record = record.model_copy(update={"content": content})
        row = record.to_store_row()
        emb = row.get("embedding")
        embedding_json = json.dumps(emb) if emb is not None else None
        archived = row.get("archived", 0)
        run_id = row.get("run_id", "") or ""
        ns = _norm_namespace(namespace)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory
                (memory_id, memory_type, content, tags, timestamp, source_task, embedding, run_id, archived, namespace)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["memory_id"],
                    row["memory_type"],
                    row["content"],
                    row["tags"],
                    row["timestamp"],
                    row["source_task"],
                    embedding_json,
                    run_id,
                    archived,
                    ns,
                ),
            )
        return row["memory_id"]

    def retrieve(self, memory_id: str, namespace: str | None = None) -> MemoryRecord | None:
        """Retrieve a single record by id."""
        ns = _norm_namespace(namespace)
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT memory_id, memory_type, content, tags, timestamp, source_task, embedding, run_id, archived,
                       COALESCE(namespace, '') AS namespace
                FROM memory WHERE memory_id = ? AND COALESCE(namespace, '') = ?
                """,
                (memory_id, ns),
            )
            row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d.pop("namespace", None)
        return _row_to_record(d)

    def delete(self, memory_id: str, namespace: str | None = None) -> bool:
        """Delete a record. Returns True if something was deleted."""
        ns = _norm_namespace(namespace)
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM memory WHERE memory_id = ? AND COALESCE(namespace, '') = ?",
                (memory_id, ns),
            )
            return cur.rowcount > 0

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
        """List records, optionally filtered by type, tag, archived, run_id, namespace, with limit/offset."""
        ns = _norm_namespace(namespace)
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            conditions = ["COALESCE(namespace, '') = ?"]
            params: list = [ns]
            if memory_type is not None:
                conditions.append("memory_type = ?")
                params.append(memory_type.value)
            if tag_contains:
                conditions.append("tags LIKE ?")
                params.append(f"%{tag_contains}%")
            if not include_archived:
                conditions.append("COALESCE(archived, 0) = 0")
            if run_id_filter is not None:
                conditions.append("run_id = ?")
                params.append(run_id_filter)
            where = " WHERE " + " AND ".join(conditions)
            params.extend([limit, offset])
            cur = conn.execute(
                f"""
                SELECT memory_id, memory_type, content, tags, timestamp, source_task, embedding,
                       COALESCE(run_id, '') as run_id, COALESCE(archived, 0) as archived,
                       COALESCE(namespace, '') as namespace
                FROM memory{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?
                """,
                params,
            )
            rows = cur.fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d.pop("namespace", None)
            out.append(_row_to_record(d))
        return out

    def list_all_ids(self, memory_type: MemoryType | None = None, namespace: str | None = None) -> list[str]:
        """List all memory ids (for index sync)."""
        ns = _norm_namespace(namespace)
        with self._conn() as conn:
            if memory_type is not None:
                cur = conn.execute(
                    """
                    SELECT memory_id FROM memory
                    WHERE memory_type = ? AND COALESCE(namespace, '') = ?
                    """,
                    (memory_type.value, ns),
                )
            else:
                cur = conn.execute(
                    "SELECT memory_id FROM memory WHERE COALESCE(namespace, '') = ?",
                    (ns,),
                )
            return [r[0] for r in cur.fetchall()]

    def set_archived(self, memory_id: str, archived: bool = True, namespace: str | None = None) -> bool:
        """v1.8: Mark a record as archived (e.g. after consolidation)."""
        ns = _norm_namespace(namespace)
        with self._conn() as conn:
            cur = conn.execute(
                """
                UPDATE memory SET archived = ?
                WHERE memory_id = ? AND COALESCE(namespace, '') = ?
                """,
                (1 if archived else 0, memory_id, ns),
            )
            return cur.rowcount > 0

    def purge_namespace(self, namespace: str) -> None:
        """Remove all memory rows for a logical namespace (e.g. when a project is deleted)."""
        if not namespace or not str(namespace).strip():
            return
        with self._conn() as conn:
            conn.execute("DELETE FROM memory WHERE namespace = ?", (namespace,))


def _row_to_record(row: dict) -> MemoryRecord:
    tags_str = row.get("tags") or ""
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    emb_raw = row.get("embedding")
    embedding = json.loads(emb_raw) if isinstance(emb_raw, str) and emb_raw else None
    archived = row.get("archived")
    if archived is None and "archived" not in row:
        archived = 0
    return MemoryRecord(
        id=row["memory_id"],
        memory_type=MemoryType(row["memory_type"]),
        content=row["content"],
        tags=tags,
        timestamp=datetime.fromisoformat(row["timestamp"]),
        source_task=row.get("source_task") or "",
        embedding=embedding,
        run_id=row.get("run_id") or "",
        archived=bool(archived) if isinstance(archived, (int, bool)) else False,
    )


def generate_memory_id() -> str:
    """Generate a unique memory id."""
    return str(uuid.uuid4())


_default_store: MemoryStore | None = None


def get_default_store() -> MemoryStore:
    """Return the default process-wide memory store (for tools)."""
    global _default_store
    if _default_store is None:
        _default_store = MemoryStore()
    return _default_store
