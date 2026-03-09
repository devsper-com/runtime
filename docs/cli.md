# CLI Reference

The Hivemind CLI is invoked as **`hivemind`** (installed with the `hivemind-ai` package). Run `hivemind --help` or `hivemind <command> --help` for usage and examples.

## Commands

### `hivemind init`

Sets up a new project in the current directory.

**Behavior:**

- Creates `hivemind.toml` with sensible defaults (workers, models, memory, tools).
- Optionally creates an example `workflow.hivemind.toml` and a `dataset/` folder for data workflows.
- Use after cloning or starting a new project so `hivemind run` and other commands find config.

**Example:**

```bash
hivemind init
```

**Exit code:** 0 on success.

---

### `hivemind doctor`

Verifies the environment and configuration.

**Behavior:**

- Checks for required API keys (e.g. `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` depending on provider).
- Validates project config file (e.g. `hivemind.toml`) if present.
- Reports tool registry status (built-in and plugin tools).
- Use to debug "not configured" or missing-provider issues before running tasks.

**Example:**

```bash
hivemind doctor
```

**Exit code:** 0 if checks pass, non-zero if something is missing or invalid.

---

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

### `hivemind query "query text"`

Queries the **knowledge graph**: entity search and relationship traversal over stored memory.

**Examples:**

```bash
hivemind query "diffusion models"
hivemind query "transformer"
```

**Behavior:**

- Loads the default memory store, builds the knowledge graph from it, and runs entity search for the query text.
- Prints matching entities (concepts, datasets, methods), relationships (edges), and document IDs that mention them.
- Exit code: 0.

---

### `hivemind workflow <name>`

Runs a **workflow** by name. Workflow definitions are read from `workflow.hivemind.toml` (or `hivemind.toml`) in the current or parent directory.

**Example workflow file (`workflow.hivemind.toml`):**

```toml
[workflow]
name = "research_pipeline"
steps = ["corpus_builder", "topic_extraction", "citation_graph", "literature_review"]
```

**Examples:**

```bash
hivemind workflow research_pipeline
```

**Behavior:**

- Loads the workflow with the given name; steps are run in order (each step depends on the previous).
- Uses the same executor/agent stack as `hivemind run` (with config for worker model, tools, memory).
- Prints each task ID and result.
- Exit code: 0 on success, 1 if the workflow is not found or has no steps.

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

### `hivemind credentials` (set | list | delete | migrate | export) {#credentials}

Manages API keys and secrets using the **OS keychain (keyring)** only. Credentials are never stored in config files.

| Subcommand | Description |
|------------|-------------|
| `set <provider> <key>` | Prompt for a value and store it in the keyring (e.g. `hivemind credentials set openai api_key`). |
| `list` | List stored credentials (provider and key only; values are never shown). |
| `delete <provider> <key>` | Remove a credential from the keyring. |
| `migrate` | Read credentials from the current project’s `.env` and TOML and store them in the keyring. Does not remove them from `.env`; you can do that manually afterward. |
| `export <provider>` | Print the provider’s stored credentials as env-style lines (`KEY=value`), suitable for `eval` or appending to `.env`. |

**Providers:** `openai`, `anthropic`, `github`, `gemini`, `azure`, `azure_anthropic`. Keys vary by provider (e.g. `api_key`, `token`, `endpoint`, `deployment`, `api_version`).

**Examples:**

```bash
hivemind credentials set openai api_key
hivemind credentials list
hivemind credentials migrate
hivemind credentials export azure
eval "$(hivemind credentials export azure)"
hivemind credentials delete openai api_key
```

Config resolution injects credentials from the keyring into the environment when not already set, so existing provider code works without changes.

---

### `hivemind completion` (bash | zsh)

Prints a shell completion script so you can use tab completion for commands and options.

**Examples:**

```bash
# Bash: add to ~/.bashrc
eval "$(hivemind completion bash)"

# Zsh: add to ~/.zshrc
eval "$(hivemind completion zsh)"
```

You can also use `hivemind --print-completion bash` (or `zsh`) for the same output.

---

### `hivemind graph` [run_id]

Exports the task dependency graph for a run as a **Mermaid** diagram. If `run_id` is omitted, uses the latest run.

**Examples:**

```bash
hivemind graph
hivemind graph abc123-run-id
```

---

### `hivemind replay` [run_id]

Reconstructs swarm execution from the event log (deterministic replay). With no `run_id`, lists recent run IDs.

**Examples:**

```bash
hivemind replay
hivemind replay abc123-run-id
```

---

### `hivemind cache` (stats | clear)

Shows or clears the task result cache.

**Examples:**

```bash
hivemind cache stats
hivemind cache clear
```

---

### `hivemind analytics`

Prints tool usage statistics (count, success rate, latency).

---

### `hivemind build` ["app description"] [-o output_dir]

Autonomous application builder: generates a working repository from a short app description.

**Examples:**

```bash
hivemind build "fastapi todo app"
hivemind build "CLI for CSV analysis" -o ./myapp
```

---

### `hivemind upgrade` [--check | -y | --version VERSION]

Checks for updates and optionally upgrades the `hivemind-ai` package from PyPI.

**Examples:**

```bash
hivemind upgrade --check
hivemind upgrade -y
hivemind upgrade --version 1.2.0
```

---

### Default: no command

If you run **`hivemind`** with no subcommand, it starts the **TUI** (same as `hivemind tui`).

---

## Global behavior

- **Config:** The CLI uses Hivemind config (env > project TOML > user TOML > defaults). **Credentials** are loaded from the OS keyring (or env) and injected when config is resolved; do not put API keys in TOML. Use `hivemind credentials` to store and manage keys.
- **Project root:** Commands that run example scripts (e.g. `research`, `analyze`) resolve the project root and set `PYTHONPATH` so examples can import `hivemind` and `examples._common` / `examples._config`.
