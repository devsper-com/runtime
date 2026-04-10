"""Per-project conversation history backed by SQLite."""

from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path


class SessionHistory:
    """Stores and retrieves conversation turns for a project session.

    Storage layout:
        {storage_dir}/sessions/{session_id}.db
    """

    def __init__(self, storage_dir: Path) -> None:
        self._storage_dir = storage_dir
        self._sessions_dir = storage_dir / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._session_id: str | None = None
        self._conn: sqlite3.Connection | None = None

    def start_new_session(self) -> str:
        """Create a new session and make it active. Returns session_id."""
        if self._conn:
            self._conn.close()
        self._session_id = str(uuid.uuid4())
        db_path = self._sessions_dir / f"{self._session_id}.db"
        self._conn = self._open(db_path)
        return self._session_id

    def load_last_session(self) -> str:
        """Load the most recent session. Creates one if none exist.

        "Most recent" is determined by db file st_mtime — i.e. the session
        most recently written to. This assumes each session has its own .db
        file and that save_turn() is called during the session.
        """
        dbs = sorted(
            self._sessions_dir.glob("*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not dbs:
            return self.start_new_session()
        if self._conn:
            self._conn.close()
        self._session_id = dbs[0].stem
        self._conn = self._open(dbs[0])
        return self._session_id

    def load_session(self, session_id: str) -> str:
        """Load a specific session by ID."""
        db_path = self._sessions_dir / f"{session_id}.db"
        if not db_path.exists():
            raise FileNotFoundError(f"Session {session_id} not found")
        if self._conn:
            self._conn.close()
        self._session_id = session_id
        self._conn = self._open(db_path)
        return self._session_id

    def save_turn(self, role: str, content: str) -> None:
        """Append a turn to the active session."""
        if not self._conn or not self._session_id:
            raise RuntimeError("No active session — call start_new_session() or load_last_session() first")
        self._conn.execute(
            "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (self._session_id, role, content, time.time()),
        )
        self._conn.commit()

    def get_turns(self, session_id: str) -> list[dict]:
        """Return all turns for a session, oldest first.

        Always reads committed data via a fresh connection so callers don't
        need to hold a reference to the active session.
        """
        db_path = self._sessions_dir / f"{session_id}.db"
        if not db_path.exists():
            return []
        conn = self._open(db_path)
        try:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM turns WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        return [{"role": r[0], "content": r[1], "timestamp": r[2]} for r in rows]

    def format_history_for_context(self, max_turns: int = 10) -> str:
        """Format recent turns as a text block for swarm context injection."""
        if not self._session_id:
            return ""
        turns = self.get_turns(self._session_id)
        recent = turns[-max_turns:]
        lines = []
        for t in recent:
            role_label = t["role"].upper()
            content = t["content"][:1000] + "..." if len(t["content"]) > 1000 else t["content"]
            lines.append(f"[{role_label}]: {content}")
        return "\n\n".join(lines)

    def list_sessions(self) -> list[dict]:
        """Return all sessions, most recent first, with turn counts."""
        dbs = sorted(
            self._sessions_dir.glob("*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        result = []
        for db_path in dbs:
            session_id = db_path.stem
            conn = self._open(db_path)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM turns WHERE session_id = ?", (session_id,)
                ).fetchone()
            finally:
                conn.close()
            result.append({
                "session_id": session_id,
                "turn_count": row[0] if row else 0,
                "modified": db_path.stat().st_mtime,
            })
        return result

    def _open(self, path: Path) -> sqlite3.Connection:
        conn = sqlite3.connect(str(path))
        conn.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL
            )"""
        )
        conn.commit()
        return conn

    def close(self) -> None:
        """Close the active database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
