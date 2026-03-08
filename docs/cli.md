# CLI Reference

The Hivemind CLI is invoked as **`hivemind`** (installed with the `hivemind-ai` package).

## Commands

### `hivemind run "task description"`

Runs the swarm with the given task. The swarm plans subtasks, runs them with agents (with tools and memory if configured), and prints results.

**Examples:**

```bash
hivemind run "analyze diffusion models"
hivemind run "Summarize swarm intelligence in one paragraph."
```

**Behavior:**

- Uses config for `worker_model`, `planner_model`, `events_dir`, and memory/data paths.
- Creates an event log in the configured events directory.
- Prints each task ID and its result (truncated if long).
- Exit code: 0 on success.

**Default task:** If you run `hivemind run` with no task, it may use a default prompt (e.g. “Summarize swarm intelligence in one paragraph.”). Check `hivemind run --help` for the exact default.

---

### `hivemind research papers/`

Runs the **literature review** example on a directory of papers (e.g. PDF/DOCX).

**Examples:**

```bash
hivemind research papers/
hivemind research .
```

**Parameters:**

- `path` (positional, optional): Directory containing papers; default `.`.

**Behavior:**

- Invokes `examples/research/literature_review.py` with the given path (with project root on `PYTHONPATH`).
- Pipeline: docproc extraction → topic extraction → citation graph → swarm literature review → markdown report.
- Outputs typically under `examples/output/`.

**Exit code:** 0 on success, 1 if the script is missing or the directory is invalid.

---

### `hivemind analyze repo/`

Runs the **repository analysis** example on a codebase path.

**Examples:**

```bash
hivemind analyze path/to/repo
hivemind analyze .
```

**Parameters:**

- `path` (positional, optional): Repository root path; default `.`.

**Behavior:**

- Invokes `examples/coding/analyze_repository.py` with the given path.
- Pipeline: codebase indexer → dependency graph → architecture analyzer → API surface → swarm synthesis.
- Outputs under `examples/output/`.

**Exit code:** 0 on success, 1 if the script is missing or the path is invalid.

---

### `hivemind memory [--limit N]`

Lists memory entries from the default memory store.

**Examples:**

```bash
hivemind memory
hivemind memory --limit 50
```

**Parameters:**

- `--limit`, `-n`: Maximum number of entries to show (default 20).

**Output:**

- For each entry: memory type, id, tags, and a short content preview (~200 chars).
- “No memory entries.” if the store is empty.

**Exit code:** 0.

---

### `hivemind tui`

Launches the **terminal UI** (prompt + output, optional dashboard).

**Example:**

```bash
hivemind tui
```

**Behavior:**

- Uses configured `events_dir` for the event log.
- Main screen: prompt input and response area; you can run the swarm from the TUI.
- See [TUI documentation](tui.md) for layout and keyboard shortcuts.

**Exit code:** 0 when the user quits.

---

### Default: no command

If you run **`hivemind`** with no subcommand, it currently starts the **TUI** (same as `hivemind tui`).

---

## Global behavior

- **Config:** CLI uses Hivemind config (env > project TOML > user TOML > defaults). Set API keys and model names via env or TOML so `run`, `research`, and `analyze` use the right providers.
- **Project root:** Commands that run example scripts (e.g. `research`, `analyze`) resolve the project root and set `PYTHONPATH` so examples can import `hivemind` and `examples._common` / `examples._config`.
