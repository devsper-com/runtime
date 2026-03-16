# CLI Reference

The devsper CLI is invoked as **`devsper`** (installed with the `devsper` package). Run `devsper --help` or `devsper <command> --help` for usage and examples.

## Commands

### `devsper init`

Sets up a new project in the current directory.

**Behavior:**

- Creates `devsper.toml` with sensible defaults (workers, models, memory, tools).
- Optionally creates an example `workflow.devsper.toml` and a `dataset/` folder for data workflows.
- Use after cloning or starting a new project so `devsper run` and other commands find config.

**Example:**

```bash
devsper init
```

**Exit code:** 0 on success.

---

### `devsper doctor`

Verifies the environment and configuration.

**Behavior:**

- Checks for required API keys (e.g. `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` depending on provider).
- Validates project config file (e.g. `devsper.toml`) if present.
- Reports tool registry status (built-in and plugin tools).
- Use to debug "not configured" or missing-provider issues before running tasks.

**Example:**

```bash
devsper doctor
```

**Exit code:** 0 if checks pass, non-zero if something is missing or invalid.

---

### `devsper run "task description"`

Runs the swarm with the given task. The swarm plans subtasks, runs them with agents (with tools and memory if configured), and prints results.

**Examples:**

```bash
devsper run "analyze diffusion models"
devsper run "Summarize swarm intelligence in one paragraph."
```

**Behavior:**

- Uses config for `worker_model`, `planner_model`, `events_dir`, and memory/data paths.
- Creates an event log in the configured events directory.
- Prints each task ID and its result (truncated if long).
- Exit code: 0 on success.

**Default task:** If you run `devsper run` with no task, it may use a default prompt (e.g. “Summarize swarm intelligence in one paragraph.”). Check `devsper run --help` for the exact default.

---

### `devsper research papers/`

Runs the **literature review** example on a directory of papers (e.g. PDF/DOCX).

**Examples:**

```bash
devsper research papers/
devsper research .
```

**Parameters:**

- `path` (positional, optional): Directory containing papers; default `.`.

**Behavior:**

- Invokes `examples/research/literature_review.py` with the given path (with project root on `PYTHONPATH`).
- Pipeline: docproc extraction → topic extraction → citation graph → swarm literature review → markdown report.
- Outputs typically under `examples/output/`.

**Exit code:** 0 on success, 1 if the script is missing or the directory is invalid.

---

### `devsper analyze [run_id | path]`

**Run analysis (when argument looks like a run ID):** Builds a run report from the event log and optionally runs LLM analysis. Use a run ID from `devsper runs` (e.g. `events_2025-03-09...`).

**Repository analysis (when argument is a path):** Runs the repository analysis example on a codebase path.

**Examples:**

```bash
devsper analyze events_2025-03-09...     # run analysis (with optional --no-ai, --json)
devsper analyze events_xxx --no-ai       # stats only, no API call
devsper analyze .                        # repo analysis
devsper analyze path/to/repo             # repo analysis
```

**Parameters (run analysis):**

- `run_id_or_path` (positional, optional): Run ID for run analysis, or path (e.g. `.`) for repo analysis.
- `--no-ai` — Skip LLM analysis; show stats only.
- `--json` — Output raw RunReport as JSON.

**Behavior (run analysis):**

- Loads events from the configured events directory, builds RunReport (timeline, critical path, bottleneck, peak parallelism, cost estimate).
- Prints Rich report (overview, timeline table, critical path, tool usage). If not `--no-ai`, streams plain-English LLM analysis.
- Exit code: 1 if run_id not found or event log empty.

**Behavior (repo analysis):** Same as before: invokes `examples/coding/analyze_repository.py` with the given path.

---

### `devsper run-analyze <run_id> [--no-ai] [--json]`

Explicit **run analysis** command. Same as `devsper analyze <run_id>` when the argument is a run ID.

**Examples:**

```bash
devsper run-analyze events_2025-03-09...
devsper run-analyze events_xxx --no-ai --json
```

---

### `devsper runs [run_id] [--limit N] [--failed] [--json]`

Lists **run history** (recorded at each SWARM_FINISHED) or shows a single run’s report.

**Examples:**

```bash
devsper runs
devsper runs --limit 10 --failed
devsper runs --json
devsper runs events_2025-03-09...    # same as run-analyze <run_id> --no-ai
```

**Parameters:**

- `run_id` (positional, optional): If given, show report for this run (no AI; same as `run-analyze <run_id> --no-ai`).
- `--limit`, `-n` — Max runs to list (default 20).
- `--failed` — Only list runs with at least one failed task.
- `--json` — Output runs list as JSON.

**Behavior:**

- Table columns: Run ID (short), Task (truncated), Strategy, Status (✓ completed / ✗ failed / ⚠ partial), Duration, Tasks, Cost, Date.
- Run history is stored in `~/.config/devsper/runs.db`.

---

### `devsper query "query text"`

Queries the **knowledge graph**: entity search and relationship traversal over stored memory.

**Examples:**

```bash
devsper query "diffusion models"
devsper query "transformer"
```

**Behavior:**

- Loads the default memory store, builds the knowledge graph from it, and runs entity search for the query text.
- Prints matching entities (concepts, datasets, methods), relationships (edges), and document IDs that mention them.
- Exit code: 0.

---

### `devsper workflow` (list, validate, run)

Workflow definitions are read from `workflow.devsper.toml` (or `devsper.toml`) in the current or parent directory. As of v1.4, workflows support **branching**, **typed outputs**, and **explicit dependencies**.

**Subcommands / usage:**

- **`devsper workflow list`** — List all defined workflows (name, version, step count, description).
- **`devsper workflow validate <name>`** — Validate a workflow (references, DAG, conditions). Exit 0 if valid, 1 if errors. Uses Rich: ✓ for pass, ✗ for errors, ⚠ for warnings.
- **`devsper workflow run <name> [--input KEY=VALUE ...]`** — Run a workflow with optional runtime inputs. After completion prints a summary table (step id, status, duration) and step outputs.
- **`devsper workflow <name>`** — Same as `devsper workflow run <name>` (backward compatible).

**Example workflow file (v1.4 format):**

```toml
[workflow.summarize_and_route]
name = "Summarize and Route"
version = "1.0"

[[workflow.summarize_and_route.steps]]
id = "summarize"
task = "Summarize the following document: {input.text}"

[[workflow.summarize_and_route.steps]]
id = "classify"
task = "Classify this summary into one of: technical, business, legal. Summary: {steps.summarize.result}"
depends_on = ["summarize"]

[[workflow.summarize_and_route.steps.output_schema]]
name = "category"
type = "str"
required = true

[[workflow.summarize_and_route.steps]]
id = "technical_deep_dive"
task = "Perform a deep technical analysis: {steps.summarize.result}"
depends_on = ["classify"]

[workflow.summarize_and_route.steps.if]
expression = "steps.classify.category == 'technical'"
```

**Legacy format (still supported):** `[workflow]` with `name` and `steps = ["step1", "step2"]` runs steps in order with auto-generated ids.

**Examples:**

```bash
devsper workflow list
devsper workflow validate summarize_and_route
devsper workflow run summarize_and_route --input text="Your document here."
devsper workflow research_pipeline
```

**Behavior:**

- **list:** Prints a table of workflows (name, version, steps, description).
- **validate:** Checks `depends_on` references, DAG cycles, template/condition references, and reports dead output warnings.
- **run:** Validates required inputs, runs steps in dependency order (waves); steps in the same wave run in parallel. Steps with `if:` are skipped when the condition is false; dependents of skipped steps are also skipped. Prints summary table and step results. Exit 0 on success, 1 if workflow not found or validation fails.

---

### `devsper memory` [--limit N] | `devsper memory consolidate` (v1.8)

**List (default):** Lists memory entries from the default memory store. **Consolidate (v1.8):** Clusters similar memories, summarizes clusters, archives originals (`--dry-run`, `--min-cluster-size`); requires `[data]` extra.

**Examples:**

```bash
devsper memory
devsper memory --limit 50
```

**Parameters:**

- `--limit`, `-n`: Maximum number of entries to show (default 20).

**Output:**

- For each entry: memory type, id, tags, and a short content preview (~200 chars).
- “No memory entries.” if the store is empty.

**Exit code:** 0.

---

### `devsper synthesize "query"` (v1.8)

Answers a question using all memory across runs (and optional knowledge graph). Streams synthesis; cites `[run:SHORT_ID]`. Options: `--no-kg`, `--json`, `--since DATE`.

---

### `devsper tui`

Launches the **terminal UI** (prompt + output, optional dashboard).

**Example:**

```bash
devsper tui
```

**Behavior:**

- Uses configured `events_dir` for the event log.
- Main screen: prompt input and response area; you can run the swarm from the TUI.
- See [TUI documentation](tui) for layout and keyboard shortcuts.

**Exit code:** 0 when the user quits.

---

### `devsper credentials` (set | list | delete | migrate | export) {#credentials}

Manages API keys and secrets using the **OS keychain (keyring)** only. Credentials are never stored in config files.

| Subcommand | Description |
|------------|-------------|
| `set <provider> <key>` | Prompt for a value and store it in the keyring (e.g. `devsper credentials set openai api_key`). |
| `list` | List stored credentials (provider and key only; values are never shown). |
| `delete <provider> <key>` | Remove a credential from the keyring. |
| `migrate` | Read credentials from the current project’s `.env` and TOML and store them in the keyring. Does not remove them from `.env`; you can do that manually afterward. |
| `export <provider>` | Print the provider’s stored credentials as env-style lines (`KEY=value`), suitable for `eval` or appending to `.env`. |

**Providers:** `openai`, `anthropic`, `github`, `gemini`, `azure`, `azure_anthropic`. Keys vary by provider (e.g. `api_key`, `token`, `endpoint`, `deployment`, `api_version`).

**Examples:**

```bash
devsper credentials set openai api_key
devsper credentials list
devsper credentials migrate
devsper credentials export azure
eval "$(devsper credentials export azure)"
devsper credentials delete openai api_key
```

Config resolution injects credentials from the keyring into the environment when not already set, so existing provider code works without changes.

---

### `devsper completion` (bash | zsh)

Prints a shell completion script so you can use tab completion for commands and options.

**Examples:**

```bash
# Bash: add to ~/.bashrc
eval "$(devsper completion bash)"

# Zsh: add to ~/.zshrc
eval "$(devsper completion zsh)"
```

You can also use `devsper --print-completion bash` (or `zsh`) for the same output.

---

### `devsper graph` [run_id]

Exports the task dependency graph for a run as a **Mermaid** diagram. If `run_id` is omitted, uses the latest run.

**Examples:**

```bash
devsper graph
devsper graph abc123-run-id
```

---

### `devsper replay` [run_id]

Reconstructs swarm execution from the event log (deterministic replay). With no `run_id`, lists recent run IDs.

**Examples:**

```bash
devsper replay
devsper replay abc123-run-id
```

---

### `devsper cache` (stats | clear | tune)

Shows, clears, or tunes the task result cache.

**Subcommands:**

- **`stats`** — Cached task count (exact match). When the semantic cache is enabled and has entries, also shows: semantic cache threshold, total entries, and placeholders for hit rate / avg similarity / est. tokens saved (when available).
- **`clear`** — Deletes all cached results (exact and semantic).
- **`tune`** — Re-evaluates the last 50 semantic cache entries at different similarity thresholds (0.85–0.95) so you can calibrate `similarity_threshold`; use `--threshold` to set the current threshold for comparison.

**Examples:**

```bash
devsper cache stats
devsper cache clear
devsper cache tune --threshold 0.90
```

**Environment:** `DEVSPER_DISABLE_SEMANTIC_CACHE=1` disables semantic cache lookup in the executor (for debugging).

---

### `devsper analytics`

Prints tool usage statistics (count, success rate, latency).

---

### `devsper build` ["app description"] [-o output_dir]

Autonomous application builder: generates a working repository from a short app description.

**Examples:**

```bash
devsper build "fastapi todo app"
devsper build "CLI for CSV analysis" -o ./myapp
```

---

### `devsper upgrade` [--check | -y | --version VERSION]

Checks for updates and optionally upgrades the `devsper` package from PyPI.

**Examples:**

```bash
devsper upgrade --check
devsper upgrade -y
devsper upgrade --version 1.2.0
```

---

### Default: no command

If you run **`devsper`** with no subcommand, it starts the **TUI** (same as `devsper tui`).

---

## Global behavior

- **Config:** The CLI uses devsper config (env > project TOML > user TOML > defaults). **Credentials** are loaded from the OS keyring (or env) and injected when config is resolved; do not put API keys in TOML. Use `devsper credentials` to store and manage keys.
- **Project root:** Commands that run example scripts (e.g. `research`, `analyze`) resolve the project root and set `PYTHONPATH` so examples can import `devsper` and `examples._common` / `examples._config`.
