"""
Persistent memory store: SQLite-backed store, retrieve, delete, list.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from hivemind.memory.memory_types import MemoryRecord, MemoryType


def _default_db_path() -> str:
    from hivemind.config import get_config

    base = os.environ.get("HIVEMIND_DATA_DIR") or get_config().data_dir
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "memory.db")


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

    def store(self, record: MemoryRecord) -> str:
        """Store a memory record. Returns record id."""
        row = record.to_store_row()
        emb = row.get("embedding")
        embedding_json = json.dumps(emb) if emb is not None else None
        archived = row.get("archived", 0)
        run_id = row.get("run_id", "") or ""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory
                (memory_id, memory_type, content, tags, timestamp, source_task, embedding, run_id, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
        return row["memory_id"]

    def retrieve(self, memory_id: str) -> MemoryRecord | None:
        """Retrieve a single record by id."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT memory_id, memory_type, content, tags, timestamp, source_task, embedding, run_id, archived FROM memory WHERE memory_id = ?",
                (memory_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _row_to_record(dict(row))

    def delete(self, memory_id: str) -> bool:
        """Delete a record. Returns True if something was deleted."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memory WHERE memory_id = ?", (memory_id,))
            return cur.rowcount > 0

    def list_memory(
        self,
        memory_type: MemoryType | None = None,
        limit: int = 100,
        offset: int = 0,
        tag_contains: str | None = None,
        include_archived: bool = False,
        run_id_filter: str | None = None,
    ) -> list[MemoryRecord]:
        """List records, optionally filtered by type, tag, archived, run_id, with limit/offset."""
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            conditions = []
            params = []
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
            where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            params.extend([limit, offset])
            cur = conn.execute(
                f"""
                SELECT memory_id, memory_type, content, tags, timestamp, source_task, embedding,
                       COALESCE(run_id, '') as run_id, COALESCE(archived, 0) as archived
                FROM memory{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?
                """,
                params,
            )
            rows = cur.fetchall()
        return [_row_to_record(dict(r)) for r in rows]

    def list_all_ids(self, memory_type: MemoryType | None = None) -> list[str]:
        """List all memory ids (for index sync)."""
        with self._conn() as conn:
            if memory_type is not None:
                cur = conn.execute(
                    "SELECT memory_id FROM memory WHERE memory_type = ?",
                    (memory_type.value,),
                )
            else:
                cur = conn.execute("SELECT memory_id FROM memory")
            return [r[0] for r in cur.fetchall()]

    def set_archived(self, memory_id: str, archived: bool = True) -> bool:
        """v1.8: Mark a record as archived (e.g. after consolidation)."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE memory SET archived = ? WHERE memory_id = ?",
                (1 if archived else 0, memory_id),
            )
            return cur.rowcount > 0


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
