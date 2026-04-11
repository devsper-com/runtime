# devsper Coding Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive coding REPL to devsper so `devsper` (no args) launches a swarm-backed coding agent that knows your project, reads `devsper.md`, maintains per-project conversation history, and streams tool calls live to the terminal — making devsper a peer to Claude Code / Opencode.

**Architecture:** The existing multi-agent Swarm remains the execution engine. A new `devsper/workspace/` package adds: `WorkspaceContext` (project discovery + devsper.md loading), `SessionHistory` (SQLite conversation persistence), `CallbackEventLog` (event tap into the existing EventLog to stream tool/task events), and `CodeREPL` (REPL loop). Context (devsper.md + conversation history) is injected by prepending a structured block to each task string — no Swarm signature changes needed. Memory is scoped per-project by overriding the namespace on the loaded config before instantiating Swarm.

**Tech Stack:** Python 3.12+, `sqlite3` (stdlib), `rich` (already a core dep), `difflib` (stdlib), existing `Swarm`/`EventLog`/`Tool`/`ToolRegistry` infrastructure.

---

## File Map

**New files:**
- `devsper/workspace/__init__.py` — re-exports WorkspaceContext, SessionHistory, CodeREPL
- `devsper/workspace/context.py` — WorkspaceContext dataclass + discover()
- `devsper/workspace/session.py` — SessionHistory (SQLite)
- `devsper/workspace/display.py` — CallbackEventLog + ToolCallDisplay (Rich)
- `devsper/workspace/repl.py` — CodeREPL (main loop)
- `devsper/tools/workspace/__init__.py` — auto-registers StrReplaceFile
- `devsper/tools/workspace/str_replace.py` — StrReplaceFile tool

**Modified files:**
- `devsper/cli/main.py` — default (no args) → `_run_repl()`; add `--new`/`--session` flags; add `init --md` to init subparser
- `devsper/cli/init.py` — add `run_init_md(project_root: Path) -> int`

**Test files:**
- `tests/test_workspace_context.py`
- `tests/test_session_history.py`
- `tests/test_str_replace_tool.py`
- `tests/test_repl_display.py`

---

## Task 1: StrReplaceFile Tool

The core surgical edit tool. Must return `str` (per `Tool` base class contract). Returns a JSON string containing the unified diff + line counts.

**Files:**
- Create: `devsper/tools/workspace/__init__.py`
- Create: `devsper/tools/workspace/str_replace.py`
- Test: `tests/test_str_replace_tool.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_str_replace_tool.py
import json
import tempfile
import textwrap
from pathlib import Path
import pytest

from devsper.tools.workspace.str_replace import StrReplaceFile


@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("def hello():\n    return 'world'\n")
    return f


def test_basic_replacement(tmp_file):
    tool = StrReplaceFile()
    result = json.loads(tool.run(file=str(tmp_file), old_str="'world'", new_str="'universe'"))
    assert result["lines_added"] >= 0
    assert result["lines_removed"] >= 0
    assert "diff" in result
    assert tmp_file.read_text() == "def hello():\n    return 'universe'\n"


def test_old_str_not_found(tmp_file):
    tool = StrReplaceFile()
    result = json.loads(tool.run(file=str(tmp_file), old_str="NOT_HERE", new_str="x"))
    assert result["error"] == "old_str not found in file"


def test_old_str_ambiguous(tmp_file):
    tmp_file.write_text("x = 1\nx = 1\n")
    tool = StrReplaceFile()
    result = json.loads(tool.run(file=str(tmp_file), old_str="x = 1", new_str="x = 2"))
    assert result["error"] == "old_str matches multiple locations — be more specific"


def test_relative_path_resolved(tmp_path, monkeypatch):
    f = tmp_path / "foo.py"
    f.write_text("a = 1\n")
    monkeypatch.chdir(tmp_path)
    tool = StrReplaceFile()
    result = json.loads(tool.run(file="foo.py", old_str="a = 1", new_str="a = 2"))
    assert "error" not in result
    assert f.read_text() == "a = 2\n"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/rkamesh/dev/devsper/runtime
uv run pytest tests/test_str_replace_tool.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'devsper.tools.workspace'`

- [ ] **Step 3: Create the tool package and implementation**

Create `devsper/tools/workspace/__init__.py`:
```python
"""Workspace-aware coding tools (str_replace, etc.)."""

from devsper.tools.workspace.str_replace import StrReplaceFile
from devsper.tools.registry import register

register(StrReplaceFile())
```

Create `devsper/tools/workspace/str_replace.py`:
```python
"""Surgical find-and-replace tool for the coding REPL."""

import difflib
import json
from pathlib import Path

from devsper.tools.base import Tool


class StrReplaceFile(Tool):
    """Replace an exact string in a file exactly once. Returns a JSON diff."""

    name = "str_replace_file"
    description = (
        "Surgically replace an exact string in a file. "
        "old_str must appear exactly once. Returns a unified diff."
    )
    category = "workspace"
    input_schema = {
        "file": {"type": "string", "description": "Path to the file (relative or absolute)"},
        "old_str": {"type": "string", "description": "The exact string to replace (must appear once)"},
        "new_str": {"type": "string", "description": "The replacement string"},
    }

    def run(self, **kwargs) -> str:  # noqa: D102
        file: str = kwargs["file"]
        old_str: str = kwargs["old_str"]
        new_str: str = kwargs["new_str"]

        path = Path(file) if Path(file).is_absolute() else Path.cwd() / file
        try:
            original = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return json.dumps({"error": f"file not found: {file}"})

        count = original.count(old_str)
        if count == 0:
            return json.dumps({"error": "old_str not found in file"})
        if count > 1:
            return json.dumps({"error": "old_str matches multiple locations — be more specific"})

        updated = original.replace(old_str, new_str, 1)
        path.write_text(updated, encoding="utf-8")

        original_lines = original.splitlines(keepends=True)
        updated_lines = updated.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(
                original_lines,
                updated_lines,
                fromfile=f"a/{path.name}",
                tofile=f"b/{path.name}",
                n=3,
            )
        )
        diff_str = "".join(diff_lines)
        added = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

        return json.dumps({
            "file": str(path),
            "lines_added": added,
            "lines_removed": removed,
            "diff": diff_str,
        })
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_str_replace_tool.py -v
```
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devsper/tools/workspace/ tests/test_str_replace_tool.py
git commit -m "feat(tools): add str_replace_file tool for surgical file edits"
```

---

## Task 2: WorkspaceContext

Discovers the project root and loads `devsper.md`.

**Files:**
- Create: `devsper/workspace/__init__.py`
- Create: `devsper/workspace/context.py`
- Test: `tests/test_workspace_context.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workspace_context.py
import textwrap
from pathlib import Path
import pytest

from devsper.workspace.context import WorkspaceContext


@pytest.fixture
def git_project(tmp_path):
    """A directory with a .git folder."""
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def md_project(tmp_path):
    """A directory with devsper.md."""
    md = tmp_path / "devsper.md"
    md.write_text("# My Project\n\nDo things.\n")
    return tmp_path


def test_discovers_git_root(git_project):
    subdir = git_project / "src" / "pkg"
    subdir.mkdir(parents=True)
    ctx = WorkspaceContext.discover(subdir)
    assert ctx.project_root == git_project


def test_devsper_md_root_takes_priority(tmp_path):
    """If both .git and devsper.md exist, devsper.md location wins (it can be nested)."""
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "devsper.md").write_text("# Sub Project\n")
    ctx = WorkspaceContext.discover(sub)
    assert ctx.project_root == sub
    assert ctx.md_content == "# Sub Project\n"


def test_md_content_loaded(md_project):
    ctx = WorkspaceContext.discover(md_project)
    assert ctx.md_content == "# My Project\n\nDo things.\n"


def test_bare_directory_fallback(tmp_path):
    ctx = WorkspaceContext.discover(tmp_path)
    assert ctx.project_root == tmp_path


def test_project_id_is_consistent(git_project):
    ctx1 = WorkspaceContext.discover(git_project)
    ctx2 = WorkspaceContext.discover(git_project)
    assert ctx1.project_id == ctx2.project_id
    assert len(ctx1.project_id) == 16  # sha256[:16]


def test_project_name_is_dir_name(git_project):
    ctx = WorkspaceContext.discover(git_project)
    assert ctx.project_name == git_project.name


def test_storage_dir_is_under_user_data(git_project):
    ctx = WorkspaceContext.discover(git_project)
    assert ctx.storage_dir.parts[-3] == "devsper"
    assert ctx.storage_dir.parts[-2] == "projects"
    assert ctx.storage_dir.name == ctx.project_id
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_workspace_context.py -v 2>&1 | head -15
```
Expected: `ModuleNotFoundError: No module named 'devsper.workspace'`

- [ ] **Step 3: Create workspace package and WorkspaceContext**

Create `devsper/workspace/__init__.py`:
```python
"""Workspace-aware coding REPL infrastructure."""

from devsper.workspace.context import WorkspaceContext
from devsper.workspace.session import SessionHistory

__all__ = ["WorkspaceContext", "SessionHistory"]
```

Create `devsper/workspace/context.py`:
```python
"""WorkspaceContext — project root discovery and devsper.md loading."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspaceContext:
    """Resolved information about the current project workspace."""

    project_root: Path
    project_id: str        # sha256(project_root)[:16]
    project_name: str      # project_root.name
    md_content: str | None # contents of devsper.md if present
    storage_dir: Path      # ~/.local/share/devsper/projects/{project_id}/

    @classmethod
    def discover(cls, cwd: Path) -> "WorkspaceContext":
        """Walk upward from cwd to find project root.

        Priority:
        1. First directory containing devsper.md (upward from cwd, inclusive)
        2. First directory containing .git/  (upward from cwd, inclusive)
        3. cwd itself as fallback
        """
        root: Path | None = None
        md_content: str | None = None

        # Walk up looking for devsper.md first
        for parent in [cwd, *cwd.parents]:
            md_path = parent / "devsper.md"
            if md_path.is_file():
                root = parent
                md_content = md_path.read_text(encoding="utf-8")
                break

        # If not found, walk up looking for .git
        if root is None:
            for parent in [cwd, *cwd.parents]:
                if (parent / ".git").exists():
                    root = parent
                    break

        # Final fallback
        if root is None:
            root = cwd

        project_id = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        storage_dir = Path.home() / ".local" / "share" / "devsper" / "projects" / project_id

        return cls(
            project_root=root.resolve(),
            project_id=project_id,
            project_name=root.resolve().name,
            md_content=md_content,
            storage_dir=storage_dir,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_workspace_context.py -v
```
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devsper/workspace/__init__.py devsper/workspace/context.py tests/test_workspace_context.py
git commit -m "feat(workspace): add WorkspaceContext for project discovery and devsper.md loading"
```

---

## Task 3: SessionHistory

Per-project conversation history using stdlib `sqlite3`.

**Files:**
- Create: `devsper/workspace/session.py`
- Test: `tests/test_session_history.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_history.py
import time
from pathlib import Path
import pytest

from devsper.workspace.session import SessionHistory


@pytest.fixture
def storage_dir(tmp_path):
    d = tmp_path / "project-abc123"
    d.mkdir()
    return d


def test_start_new_session(storage_dir):
    sh = SessionHistory(storage_dir)
    session_id = sh.start_new_session()
    assert len(session_id) == 36  # UUID format
    sessions_dir = storage_dir / "sessions"
    assert sessions_dir.is_dir()


def test_save_and_load_turns(storage_dir):
    sh = SessionHistory(storage_dir)
    session_id = sh.start_new_session()
    sh.save_turn("user", "hello")
    sh.save_turn("assistant", "hi there")
    turns = sh.get_turns(session_id)
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "hello"
    assert turns[1]["role"] == "assistant"


def test_load_last_session(storage_dir):
    sh = SessionHistory(storage_dir)
    sh.start_new_session()
    sh.save_turn("user", "first session")
    time.sleep(0.01)
    sh.start_new_session()
    sh.save_turn("user", "second session")

    sh2 = SessionHistory(storage_dir)
    session_id = sh2.load_last_session()
    turns = sh2.get_turns(session_id)
    assert turns[0]["content"] == "second session"


def test_no_last_session_returns_new(storage_dir):
    sh = SessionHistory(storage_dir)
    session_id = sh.load_last_session()
    assert session_id is not None  # creates new session when none exist


def test_list_sessions(storage_dir):
    sh = SessionHistory(storage_dir)
    sh.start_new_session()
    sh.save_turn("user", "msg1")
    sh.start_new_session()
    sh.save_turn("user", "msg2")
    sessions = sh.list_sessions()
    assert len(sessions) == 2
    # most recent first
    assert sessions[0]["turn_count"] == 1


def test_format_history_for_context(storage_dir):
    sh = SessionHistory(storage_dir)
    sh.start_new_session()
    sh.save_turn("user", "write a function")
    sh.save_turn("assistant", "Here is the function: def foo(): pass")
    text = sh.format_history_for_context(max_turns=10)
    assert "[USER]" in text
    assert "[ASSISTANT]" in text
    assert "write a function" in text
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_session_history.py -v 2>&1 | head -15
```
Expected: `ImportError` for `devsper.workspace.session`

- [ ] **Step 3: Implement SessionHistory**

Create `devsper/workspace/session.py`:
```python
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

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def start_new_session(self) -> str:
        """Create a new session and make it active. Returns session_id."""
        if self._conn:
            self._conn.close()
        self._session_id = str(uuid.uuid4())
        db_path = self._sessions_dir / f"{self._session_id}.db"
        self._conn = self._open(db_path)
        return self._session_id

    def load_last_session(self) -> str:
        """Load the most recent session. Creates one if none exist."""
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

    # ------------------------------------------------------------------
    # Turn management
    # ------------------------------------------------------------------

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
        """Return all turns for a session, oldest first."""
        db_path = self._sessions_dir / f"{session_id}.db"
        if not db_path.exists():
            return []
        conn = self._open(db_path)
        rows = conn.execute(
            "SELECT role, content, timestamp FROM turns WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
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
            # Truncate very long turns to avoid prompt bloat
            content = t["content"][:1000] + "..." if len(t["content"]) > 1000 else t["content"]
            lines.append(f"[{role_label}]: {content}")
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

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
            row = conn.execute(
                "SELECT COUNT(*) FROM turns WHERE session_id = ?", (session_id,)
            ).fetchone()
            conn.close()
            result.append({
                "session_id": session_id,
                "turn_count": row[0] if row else 0,
                "modified": db_path.stat().st_mtime,
            })
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

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
        if self._conn:
            self._conn.close()
            self._conn = None
```

- [ ] **Step 4: Update `devsper/workspace/__init__.py` to export SessionHistory**

`devsper/workspace/__init__.py` already imports `SessionHistory` from task 2. No change needed.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
uv run pytest tests/test_session_history.py -v
```
Expected: All 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add devsper/workspace/session.py tests/test_session_history.py
git commit -m "feat(workspace): add SessionHistory for per-project conversation persistence"
```

---

## Task 4: Display — CallbackEventLog + ToolCallDisplay

Taps into the existing `EventLog` event stream and renders tool/task events to the terminal using Rich.

**Files:**
- Create: `devsper/workspace/display.py`
- Test: `tests/test_repl_display.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_repl_display.py
import io
from unittest.mock import MagicMock, patch

import pytest

from devsper.workspace.display import CallbackEventLog, ToolCallDisplay, format_event_line


def test_format_event_line_tool_start():
    line = format_event_line({"type": "tool_start", "tool": "read_file", "args": {"file": "foo.py"}})
    assert "read_file" in line or "foo.py" in line


def test_format_event_line_tool_done():
    line = format_event_line({"type": "tool_done", "tool": "read_file", "result": {"lines": 42}})
    assert line is not None


def test_format_event_line_agent_start():
    line = format_event_line({"type": "agent_start", "role": "code", "description": "Write tests"})
    assert line is not None


def test_format_event_line_unknown_returns_none():
    line = format_event_line({"type": "swarm_heartbeat"})
    assert line is None


def test_callback_event_log_calls_callback():
    received = []
    cel = CallbackEventLog(callback=received.append, events_folder_path="/tmp/devsper-test-events")
    
    mock_event = MagicMock()
    mock_event.type = "TASK_STARTED"
    type(mock_event).model_dump = MagicMock(return_value={"type": "TASK_STARTED", "payload": {}})
    
    cel.append_event(mock_event)
    assert len(received) == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_repl_display.py -v 2>&1 | head -15
```
Expected: `ImportError` for `devsper.workspace.display`

- [ ] **Step 3: Implement display module**

Create `devsper/workspace/display.py`:
```python
"""Rich-based display for the coding REPL — tool call lines and diffs."""

from __future__ import annotations

import json
from typing import Callable

from devsper.utils.event_logger import EventLog


# ---------------------------------------------------------------------------
# Event formatting
# ---------------------------------------------------------------------------

def format_event_line(event: dict) -> str | None:
    """Convert a swarm event dict to a one-line display string, or None to suppress."""
    event_type = event.get("type", "")

    if event_type == "tool_start":
        tool = event.get("tool", "tool")
        args = event.get("args", {})
        detail = _first_meaningful_arg(args)
        return f"  [bold cyan]●[/] [dim]{tool}[/] {detail}..." if detail else f"  [bold cyan]●[/] [dim]{tool}[/]..."

    if event_type == "tool_done":
        tool = event.get("tool", "tool")
        result = event.get("result", {})
        detail = _summarize_result(result)
        return f"  [green]●[/] [dim]{tool}[/] {detail}" if detail else f"  [green]●[/] [dim]{tool}[/]"

    if event_type == "agent_start":
        role = event.get("role") or event.get("agent_role", "agent")
        desc = event.get("description", "")
        short = desc[:60] + "..." if len(desc) > 60 else desc
        return f"  [bold magenta]◎[/] [dim]Agent ({role})[/] {short}"

    if event_type == "agent_done":
        role = event.get("role") or event.get("agent_role", "agent")
        return f"  [green]◎[/] [dim]Agent ({role}) done[/]"

    # Suppress everything else (swarm_started, swarm_finished, etc.)
    return None


def format_diff_block(diff_str: str, file_path: str) -> str:
    """Return a Rich markup string for a unified diff."""
    if not diff_str.strip():
        return ""
    lines = []
    lines.append(f"  [bold]Editing[/] [cyan]{file_path}[/]")
    for line in diff_str.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(f"  [green]{line}[/]")
        elif line.startswith("-") and not line.startswith("---"):
            lines.append(f"  [red]{line}[/]")
        elif line.startswith("@@"):
            lines.append(f"  [bold yellow]{line}[/]")
        else:
            lines.append(f"  {line}")
    return "\n".join(lines)


def _first_meaningful_arg(args: dict) -> str:
    """Pull the most informative arg value for display."""
    for key in ("file", "path", "query", "pattern", "command", "url", "name"):
        if key in args:
            val = str(args[key])
            return val[:50] + "..." if len(val) > 50 else val
    vals = list(args.values())
    if vals:
        val = str(vals[0])
        return val[:50] + "..." if len(val) > 50 else val
    return ""


def _summarize_result(result: dict | str) -> str:
    if isinstance(result, str):
        return ""
    lines = result.get("lines", result.get("line_count", ""))
    if lines:
        return f"({lines} lines)"
    matches = result.get("matches", result.get("count", ""))
    if matches:
        return f"({matches} matches)"
    added = result.get("lines_added")
    removed = result.get("lines_removed")
    if added is not None:
        return f"+{added} -{removed}"
    return ""


# ---------------------------------------------------------------------------
# CallbackEventLog
# ---------------------------------------------------------------------------

class CallbackEventLog(EventLog):
    """EventLog subclass that calls a callback on every appended event.

    Usage::

        def on_event(event_dict: dict) -> None:
            line = format_event_line(event_dict)
            if line:
                console.print(line)

        event_log = CallbackEventLog(callback=on_event, events_folder_path="/tmp/devsper-events")
        swarm = Swarm(event_log=event_log)
    """

    def __init__(self, callback: Callable[[dict], None], **kwargs) -> None:
        super().__init__(**kwargs)
        self._callback = callback

    def append_event(self, event) -> None:  # type: ignore[override]
        super().append_event(event)
        try:
            if hasattr(event, "model_dump"):
                event_dict = event.model_dump()
            elif hasattr(event, "__dict__"):
                event_dict = event.__dict__.copy()
            else:
                event_dict = {}
            self._callback(event_dict)
        except Exception:
            pass  # Never let display errors kill the swarm


# ---------------------------------------------------------------------------
# ToolCallDisplay  (stateful Rich renderer for the REPL)
# ---------------------------------------------------------------------------

class ToolCallDisplay:
    """Accumulates and prints tool-call events using Rich."""

    def __init__(self, console=None) -> None:
        try:
            from rich.console import Console
            self._console = console or Console()
        except ImportError:
            self._console = None

    def on_event(self, event_dict: dict) -> None:
        """Receive an event dict from CallbackEventLog and render it."""
        # Special handling for str_replace_file results (show diff inline)
        if event_dict.get("type") == "tool_done" and event_dict.get("tool") == "str_replace_file":
            raw_result = event_dict.get("result", {})
            if isinstance(raw_result, str):
                try:
                    raw_result = json.loads(raw_result)
                except Exception:
                    pass
            diff = raw_result.get("diff", "") if isinstance(raw_result, dict) else ""
            file_path = raw_result.get("file", "") if isinstance(raw_result, dict) else ""
            if diff and self._console:
                self._console.print(format_diff_block(diff, file_path), markup=True)
            return

        line = format_event_line(event_dict)
        if line and self._console:
            self._console.print(line, markup=True)
        elif line:
            print(line)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_repl_display.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devsper/workspace/display.py tests/test_repl_display.py
git commit -m "feat(workspace): add CallbackEventLog and ToolCallDisplay for live REPL output"
```

---

## Task 5: CodeREPL

The main REPL loop. Wires together WorkspaceContext, SessionHistory, ToolCallDisplay, and Swarm.

**Files:**
- Create: `devsper/workspace/repl.py`
- Update: `devsper/workspace/__init__.py` — add CodeREPL export

- [ ] **Step 1: Implement CodeREPL**

No unit tests for the REPL loop itself (it's an interactive loop that wraps Swarm). Integration testing via smoke test in Step 3.

Create `devsper/workspace/repl.py`:
```python
"""Interactive coding REPL backed by the devsper multi-agent Swarm."""

from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from devsper.workspace.context import WorkspaceContext
from devsper.workspace.session import SessionHistory
from devsper.workspace.display import CallbackEventLog, ToolCallDisplay, format_diff_block


_BANNER = """
╭─ devsper {version} · {project} ──────────────────────────────────╮
│ {md_status:<55} │
│ {mem_status:<55} │
╰───────────────────────────────────────────────────────────────────╯
"""

_SLASH_COMMANDS = {
    "/exit": "Exit the REPL",
    "/quit": "Exit the REPL",
    "/new": "Start a fresh session (keeps semantic memory)",
    "/sessions": "List all sessions for this project",
    "/memory": "Show top semantic memories for this project",
    "/help": "Show this help",
}


class CodeREPL:
    """Interactive coding REPL powered by the devsper multi-agent Swarm.

    Usage::

        workspace = WorkspaceContext.discover(Path.cwd())
        session = SessionHistory(workspace.storage_dir)
        session_id = session.load_last_session()
        repl = CodeREPL(workspace, session)
        repl.start()
    """

    def __init__(
        self,
        workspace: WorkspaceContext,
        session: SessionHistory,
        new_session: bool = False,
    ) -> None:
        self._workspace = workspace
        self._session = session
        self._display = ToolCallDisplay()
        self._running = False

        if new_session:
            self._session.start_new_session()
        else:
            self._session.load_last_session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Enter the REPL loop. Blocks until the user exits."""
        self._print_banner()
        if self._workspace.md_content is None:
            self._print("  [dim]→ No devsper.md found. Run[/] [bold]devsper init --md[/] [dim]to generate project instructions.[/]")

        self._running = True
        while self._running:
            try:
                user_input = self._prompt()
            except (KeyboardInterrupt, EOFError):
                self._print("\n[dim]Bye![/]")
                break

            text = user_input.strip()
            if not text:
                continue

            if text.startswith("/"):
                self._handle_slash(text)
            else:
                self._run_turn(text)

        self._session.close()

    # ------------------------------------------------------------------
    # Slash commands
    # ------------------------------------------------------------------

    def _handle_slash(self, text: str) -> None:
        cmd = text.split()[0].lower()
        if cmd in ("/exit", "/quit"):
            self._running = False
        elif cmd == "/new":
            self._session.start_new_session()
            self._print("[dim]Started new session.[/]")
        elif cmd == "/sessions":
            self._list_sessions()
        elif cmd == "/memory":
            query = text[len("/memory"):].strip() or ""
            self._show_memory(query)
        elif cmd == "/help":
            self._show_help()
        else:
            self._print(f"[red]Unknown command:[/] {cmd}. Type [bold]/help[/] for available commands.")

    def _list_sessions(self) -> None:
        sessions = self._session.list_sessions()
        if not sessions:
            self._print("[dim]No sessions found.[/]")
            return
        self._print(f"[bold]{len(sessions)} session(s) for {self._workspace.project_name}:[/]")
        for s in sessions[:10]:
            import datetime
            ts = datetime.datetime.fromtimestamp(s["modified"]).strftime("%Y-%m-%d %H:%M")
            self._print(f"  [cyan]{s['session_id'][:8]}[/]... {ts}  ({s['turn_count']} turns)")

    def _show_memory(self, query: str) -> None:
        try:
            from devsper.memory.memory_index import MemoryIndex
            from devsper.memory.memory_store import MemoryStore
            store = MemoryStore(namespace=f"project:{self._workspace.project_id}")
            if query:
                index = MemoryIndex(store)
                memories = index.query_memory(query, top_k=5)
            else:
                memories = store.list_memory(limit=5)
            if not memories:
                self._print("[dim]No memories found for this project.[/]")
                return
            for m in memories:
                content = getattr(m, "content", str(m))
                self._print(f"  [cyan]·[/] {content[:120]}")
        except Exception as exc:
            self._print(f"[dim]Memory unavailable: {exc}[/]")

    def _show_help(self) -> None:
        self._print("[bold]Available commands:[/]")
        for cmd, desc in _SLASH_COMMANDS.items():
            self._print(f"  [cyan]{cmd:<12}[/] {desc}")

    # ------------------------------------------------------------------
    # Swarm execution
    # ------------------------------------------------------------------

    def _run_turn(self, user_message: str) -> None:
        self._session.save_turn("user", user_message)

        task = self._build_task(user_message)
        event_log = self._make_event_log()

        try:
            swarm = self._make_swarm(event_log)
        except Exception as exc:
            self._print(f"[red]Failed to initialise swarm:[/] {exc}")
            return

        try:
            result = swarm.run(task)
        except KeyboardInterrupt:
            self._print("\n[dim]Interrupted.[/]")
            return
        except Exception as exc:
            self._print(f"[red]Swarm error:[/] {exc}")
            self._session.save_turn("assistant", f"[error] {exc}")
            return

        # result is a dict[str, str] — collect all agent outputs
        output = self._extract_output(result)
        self._print_response(output)
        self._session.save_turn("assistant", output)

    def _build_task(self, user_message: str) -> str:
        """Prepend devsper.md and conversation history to the task string."""
        parts: list[str] = []

        if self._workspace.md_content:
            parts.append(
                f"<project_instructions>\n{self._workspace.md_content}\n</project_instructions>"
            )

        history = self._session.format_history_for_context(max_turns=10)
        if history:
            parts.append(f"<conversation_history>\n{history}\n</conversation_history>")

        parts.append(f"Current task: {user_message}")
        return "\n\n".join(parts)

    def _make_event_log(self) -> CallbackEventLog:
        storage_dir = self._workspace.storage_dir
        events_dir = storage_dir / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        return CallbackEventLog(
            callback=self._display.on_event,
            events_folder_path=str(events_dir),
        )

    def _make_swarm(self, event_log: CallbackEventLog):
        """Create a Swarm instance scoped to this project."""
        from devsper.config import get_config
        from devsper.swarm.swarm import Swarm

        # Deep-copy config so we don't pollute the global singleton
        try:
            cfg = copy.deepcopy(get_config())
        except Exception:
            cfg = get_config()

        # Scope memory to this project
        if hasattr(cfg, "memory") and hasattr(cfg.memory, "namespace"):
            cfg.memory.namespace = f"project:{self._workspace.project_id}"  # type: ignore[attr-defined]

        return Swarm(
            event_log=event_log,
            config=cfg,
        )

    @staticmethod
    def _extract_output(result: dict) -> str:
        """Pull a readable string from the swarm result dict."""
        if not result:
            return "(no output)"
        # result is {task_id: result_string, ...}
        parts = []
        for task_id, val in result.items():
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())
        return "\n\n".join(parts) if parts else str(result)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _print_banner(self) -> None:
        from devsper import __version__
        md_status = "reading devsper.md..." if self._workspace.md_content else "no devsper.md found"
        # Quick memory count
        try:
            from devsper.memory.memory_store import MemoryStore
            store = MemoryStore(namespace=f"project:{self._workspace.project_id}")
            count = len(store.list_memory(limit=200))
            mem_status = f"workspace memory: {count} facts loaded"
        except Exception:
            mem_status = "workspace memory: unavailable"

        banner = _BANNER.format(
            version=__version__,
            project=self._workspace.project_name,
            md_status=md_status,
            mem_status=mem_status,
        )
        self._print(banner)

    def _print(self, markup: str) -> None:
        if self._display._console:
            self._display._console.print(markup, markup=True)
        else:
            # Strip Rich markup tags for plain output
            import re
            plain = re.sub(r"\[/?[^\]]+\]", "", markup)
            print(plain)

    def _print_response(self, text: str) -> None:
        try:
            from rich.markdown import Markdown
            if self._display._console:
                self._display._console.print(Markdown(text))
                return
        except Exception:
            pass
        print(text)

    def _prompt(self) -> str:
        return input(f"\n{self._workspace.project_name}> ")
```

- [ ] **Step 2: Update workspace __init__.py to export CodeREPL**

Edit `devsper/workspace/__init__.py`:
```python
"""Workspace-aware coding REPL infrastructure."""

from devsper.workspace.context import WorkspaceContext
from devsper.workspace.session import SessionHistory
from devsper.workspace.repl import CodeREPL

__all__ = ["WorkspaceContext", "SessionHistory", "CodeREPL"]
```

- [ ] **Step 3: Smoke test the REPL import**

```bash
cd /Users/rkamesh/dev/devsper/runtime
uv run python -c "from devsper.workspace import CodeREPL, WorkspaceContext, SessionHistory; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add devsper/workspace/repl.py devsper/workspace/__init__.py
git commit -m "feat(workspace): add CodeREPL — swarm-backed interactive coding loop"
```

---

## Task 6: CLI Integration — Default REPL + `init --md`

Wire the REPL into the CLI as the default (no-args) behavior, and add `devsper init --md`.

**Files:**
- Modify: `devsper/cli/main.py` — `_run_tui()` default → `_run_repl()`; add `--new`/`--session` flags; add `init --md` to init subparser
- Modify: `devsper/cli/init.py` — add `run_init_md()`

- [ ] **Step 1: Add `_run_repl()` to `devsper/cli/main.py`**

Find the `_run_tui()` function (around line 960) and add a new function below it:

```python
def _run_repl(args: object | None = None) -> int:
    """Launch the interactive coding REPL."""
    from pathlib import Path
    from devsper.workspace import WorkspaceContext, SessionHistory, CodeREPL

    workspace = WorkspaceContext.discover(Path.cwd())
    session = SessionHistory(workspace.storage_dir)
    new_session = getattr(args, "new_session", False)
    session_id = getattr(args, "session_id", None)

    if session_id:
        try:
            session.load_session(session_id)
        except FileNotFoundError:
            print(f"Session {session_id!r} not found.", file=__import__("sys").stderr)
            return 1

    repl = CodeREPL(workspace, session, new_session=new_session)
    repl.start()
    return 0
```

- [ ] **Step 2: Change the default (no args) handler in `main()`**

In `devsper/cli/main.py`, find the line:
```python
    if not args.command:
        return _run_tui()
```
and change it to:
```python
    if not args.command:
        return _run_repl(args)
```

- [ ] **Step 3: Add `--new` and `--session` flags to the top-level parser**

In `main()`, find where global flags like `--debug`, `--trace`, `--no-color` are added to `parser` (before subparsers are created). Add after the existing flags:

```python
    parser.add_argument(
        "--new",
        dest="new_session",
        action="store_true",
        default=False,
        help="Start a fresh REPL session (keeps semantic memory)",
    )
    parser.add_argument(
        "--session",
        dest="session_id",
        metavar="SESSION_ID",
        default=None,
        help="Resume a specific past session by ID",
    )
```

- [ ] **Step 4: Add `--md` flag to the `init` subparser**

Find the `init` subparser setup in `main.py` (search for `"Set up a new project"` or `p_init`). Add:
```python
    p_init.add_argument(
        "--md",
        dest="init_md",
        action="store_true",
        default=False,
        help="Generate a devsper.md project instructions file using the LLM",
    )
```

And update the init handler (`_run_init` or inline handler) to check `args.init_md`:
```python
def _run_init_dispatch(args: object) -> int:
    if getattr(args, "init_md", False):
        from devsper.cli.init import run_init_md
        from pathlib import Path
        return run_init_md(Path.cwd())
    from devsper.cli.init import run_init
    interactive = not getattr(args, "no_interactive", False)
    return run_init(interactive=interactive)
```
Set this as the handler: `p_init.set_defaults(func=_run_init_dispatch)`

- [ ] **Step 5: Implement `run_init_md()` in `devsper/cli/init.py`**

Add at the end of `devsper/cli/init.py`:

```python
def run_init_md(project_root: Path) -> int:
    """Auto-generate devsper.md by indexing the project with an LLM."""
    import subprocess

    out_path = project_root / "devsper.md"
    if out_path.exists():
        print(f"devsper.md already exists at {out_path}. Delete it first to regenerate.")
        return 1

    print("● Scanning project structure...")

    # Collect context pieces
    context_parts: list[str] = []

    # 1. README
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = project_root / name
        if p.is_file():
            content = p.read_text(encoding="utf-8", errors="replace")[:4000]
            context_parts.append(f"## {name}\n{content}")
            break

    # 2. Package manifest
    for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "setup.py"):
        p = project_root / name
        if p.is_file():
            content = p.read_text(encoding="utf-8", errors="replace")[:2000]
            context_parts.append(f"## {name}\n{content}")
            break

    # 3. Git log
    print("● Reading git history...")
    try:
        git_out = subprocess.check_output(
            ["git", "log", "--oneline", "-20"],
            cwd=str(project_root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        context_parts.append(f"## Recent git history\n{git_out}")
    except Exception:
        pass

    # 4. Directory structure (top 2 levels)
    print("● Analysing directory structure...")
    try:
        from devsper.tools.coding.repo_structure import RepoStructureMap  # type: ignore[import]
        tool = RepoStructureMap()
        structure = tool.run(path=str(project_root), max_depth=2)
        context_parts.append(f"## Directory structure\n{structure}")
    except Exception:
        # Fallback: simple ls
        entries = [str(p.relative_to(project_root)) for p in project_root.iterdir() if not p.name.startswith(".")]
        context_parts.append("## Directory structure\n" + "\n".join(sorted(entries)[:40]))

    # 5. Existing devsper.toml if present
    toml_path = project_root / "devsper.toml"
    if toml_path.is_file():
        content = toml_path.read_text(encoding="utf-8", errors="replace")[:1500]
        context_parts.append(f"## devsper.toml\n{content}")

    print("● Drafting devsper.md with LLM...")

    context_block = "\n\n---\n\n".join(context_parts)

    system_prompt = """You are a senior engineer writing a devsper.md file for a project.
devsper.md is loaded at the start of every AI coding session to give the agent context about the project.
Write a clear, concise devsper.md with these sections (use ## headings):

## What this project is
(1-3 sentences: what it does, who uses it, core purpose)

## Commands
```bash
# Run tests:    <command>
# Lint/format:  <command>
# Build/start:  <command>
```

## Architecture
(3-5 sentences: key modules, how they connect, main patterns used)

## Conventions
(3-5 bullet points: naming, style, patterns the agent must follow)

## Areas to avoid / known issues
(bullet points: risky files, known bugs, things not to touch unless asked)

Be specific based on the project context. Do not add placeholders or TBDs. If information is missing, omit the item."""

    user_prompt = f"""Here is context about the project:\n\n{context_block}\n\nWrite the devsper.md now."""

    try:
        from devsper.utils.models import resolve_model
        from devsper.providers import generate

        model = resolve_model("auto")
        md_content = generate(
            prompt=user_prompt,
            system=system_prompt,
            model=model,
        )
    except Exception as exc:
        print(f"LLM call failed: {exc}")
        print("Writing a template devsper.md instead.")
        md_content = _default_devsper_md_template(project_root.name)

    out_path.write_text(md_content, encoding="utf-8")
    print(f"\nCreated {out_path} — review and edit before your first session.")
    return 0


def _default_devsper_md_template(project_name: str) -> str:
    return f"""# devsper.md

## What this project is
{project_name} — (describe what this project does)

## Commands
```bash
# Run tests:   <command>
# Lint:        <command>
# Build/start: <command>
```

## Architecture
(Describe key modules and how they connect)

## Conventions
- (convention 1)
- (convention 2)

## Areas to avoid / known issues
- (known issue or risky area)
"""
```

- [ ] **Step 6: Smoke test the CLI changes**

```bash
cd /Users/rkamesh/dev/devsper/runtime
uv run python -m devsper.cli --help 2>&1 | head -5
uv run python -m devsper.cli init --help 2>&1 | grep -i md
```
Expected: help shows `--new`, `--session`; init help shows `--md`.

```bash
# Test import path
uv run python -c "from devsper.cli.init import run_init_md; print('OK')"
```
Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add devsper/cli/main.py devsper/cli/init.py
git commit -m "feat(cli): default to coding REPL, add --new/--session flags, add init --md"
```

---

## Task 7: Register Workspace Tools + Wire Imports

Ensure the `str_replace_file` tool is loaded when the coding REPL starts.

**Files:**
- Modify: `devsper/tools/__init__.py` (or wherever tools are bulk-imported)

- [ ] **Step 1: Find where tools are imported**

```bash
grep -r "tools.coding\|tools.filesystem\|tools.system" /Users/rkamesh/dev/devsper/runtime/devsper --include="*.py" -l | head -5
```

- [ ] **Step 2: Import workspace tools alongside existing tools**

In the file that imports tool categories (likely `devsper/tools/__init__.py` or an auto-import file), add:
```python
import devsper.tools.workspace  # noqa: F401 — registers str_replace_file
```

If no such auto-import file exists, add the import inside `CodeREPL.__init__()` in `devsper/workspace/repl.py` (before creating the Swarm):
```python
# At top of CodeREPL._make_swarm():
try:
    import devsper.tools.workspace  # noqa: F401
except Exception:
    pass
```

- [ ] **Step 3: Verify the tool is in the registry**

```bash
uv run python -c "
import devsper.tools.workspace
from devsper.tools.registry import get_global_registry
t = get_global_registry().get('str_replace_file')
print('Tool registered:', t.name)
"
```
Expected: `Tool registered: str_replace_file`

- [ ] **Step 4: Commit**

```bash
git add devsper/tools/__init__.py devsper/workspace/repl.py
git commit -m "feat(tools): auto-register workspace tools including str_replace_file"
```

---

## Task 8: Version Bump + Integration Smoke Test

- [ ] **Step 1: Bump version to 2.8.0**

In `devsper/pyproject.toml`, find `version = "2.7.2"` and change to `version = "2.8.0"`.

In `devsper/__init__.py`, find `__version__` and update to `"2.8.0"`.

- [ ] **Step 2: Run the full test suite**

```bash
cd /Users/rkamesh/dev/devsper/runtime
uv run pytest tests/ -v --ignore=tests/integration -x 2>&1 | tail -20
```
Expected: All tests pass (new tests + existing).

- [ ] **Step 3: End-to-end workspace smoke test**

```bash
uv run python -c "
from pathlib import Path
from devsper.workspace import WorkspaceContext, SessionHistory, CodeREPL

# Verify workspace discovery works in the runtime directory
ctx = WorkspaceContext.discover(Path.cwd())
print('Project root:', ctx.project_root)
print('Project ID:', ctx.project_id)
print('Project name:', ctx.project_name)
print('devsper.md:', 'found' if ctx.md_content else 'not found')

# Verify session history
sh = SessionHistory(ctx.storage_dir)
sid = sh.start_new_session()
sh.save_turn('user', 'test message')
turns = sh.get_turns(sid)
print('Session turns:', len(turns))
sh.close()
print('All OK')
"
```
Expected: Prints project info and `All OK`.

- [ ] **Step 4: Verify `devsper init --md` works on a temp project**

```bash
uv run python -c "
import tempfile, os
from pathlib import Path
from devsper.cli.init import run_init_md

with tempfile.TemporaryDirectory() as d:
    # Create a minimal project
    p = Path(d)
    (p / 'README.md').write_text('# TestProject\nA test project.')
    (p / 'pyproject.toml').write_text('[project]\nname = \"testproject\"\nversion = \"0.1.0\"')
    
    original_cwd = os.getcwd()
    os.chdir(d)
    result = run_init_md(p)
    os.chdir(original_cwd)
    
    if result == 0:
        print('devsper.md generated OK')
    else:
        print('ERROR: run_init_md returned', result)
"
```
Expected: `devsper.md generated OK`

- [ ] **Step 5: Final commit**

```bash
git add devsper/__init__.py pyproject.toml
git commit -m "release: 2.8.0 — interactive coding REPL, devsper.md, per-project memory"
```

---

## Self-Review Checklist

- [x] **str_replace_file tool** — Task 1: creates, tests, registers ✓
- [x] **WorkspaceContext** — Task 2: discovery, md_content, project_id, storage_dir ✓
- [x] **SessionHistory** — Task 3: load_last, start_new, save_turn, format_history, list_sessions ✓
- [x] **CallbackEventLog** — Task 4: taps into EventLog.append_event(), fires callback ✓
- [x] **ToolCallDisplay** — Task 4: format_event_line(), diff rendering, on_event() ✓
- [x] **CodeREPL** — Task 5: banner, REPL loop, slash-commands, Swarm integration ✓
- [x] **Context injection** — Task 5 `_build_task()`: devsper.md + history prepended to task ✓
- [x] **Memory scoping** — Task 5 `_make_swarm()`: config.memory.namespace = project:{id} ✓
- [x] **CLI default → REPL** — Task 6: `_run_tui()` → `_run_repl(args)` ✓
- [x] **--new / --session flags** — Task 6 ✓
- [x] **init --md** — Task 6: `run_init_md()` scans project, calls LLM, writes devsper.md ✓
- [x] **str_replace_file auto-registration** — Task 7 ✓
- [x] **Version bump 2.8.0** — Task 8 ✓
- [x] **Type consistency** — `WorkspaceContext`, `SessionHistory`, `CallbackEventLog`, `ToolCallDisplay`, `CodeREPL` names consistent throughout ✓
- [x] **Tool.run() returns str** — `StrReplaceFile.run()` returns `json.dumps(...)` ✓
- [x] **No placeholders** — All steps have complete code ✓
