# CLI Reference

The `devsper` binary is the unified entry point for all runtime operations.

```
devsper <command> [flags]
```

---

## `devsper run`

Execute a workflow.

```bash
devsper run <workflow> [flags]
```

| Flag                        | Description                                          |
|-----------------------------|------------------------------------------------------|
| `--input K=V`               | Pass a named input to the workflow (repeatable).    |
| `--workers N`               | Max concurrent tasks. Default: 4.                    |
| `--cluster <addr>`          | Submit to a running cluster coordinator.             |
| `--inspect-socket <path>`   | Expose Unix socket for TUI connection.               |
| `--bus memory\|redis\|kafka` | Message bus backend. Default: memory.               |

**Examples:**

```bash
# Interpret .devsper file directly
devsper run workflow.devsper

# Pass inputs
devsper run analyze-repo.devsper --input repo_url=https://github.com/example/repo

# Run compiled bytecode
devsper run workflow.devsper.bin

# Submit to cluster
devsper run workflow.devsper --cluster 10.0.0.1:7000 --input repo_url=https://...

# Expose inspect socket for TUI
devsper run workflow.devsper --inspect-socket /tmp/devsper-abc123.sock
```

**Exit codes:** 0 on success, 1 on workflow error, 2 on configuration error.

---

## `devsper compile`

Compile a `.devsper` workflow.

```bash
devsper compile <workflow> [--embed]
```

| Flag      | Description                                                |
|-----------|------------------------------------------------------------|
| `--embed` | Produce a standalone binary instead of `.devsper.bin`.    |

**Examples:**

```bash
# Compile to bytecode (JSON IR)
devsper compile workflow.devsper
# → workflow.devsper.bin

# Compile to standalone binary
devsper compile --embed workflow.devsper
# → ./workflow  (self-contained executable)

# Run the standalone binary
./workflow --input repo_url=https://github.com/example/repo
```

Bytecode (`.devsper.bin`) is a serialized `WorkflowIr` JSON blob. It loads faster than parsing Lua at runtime and is portable across machines with the same devsper version.

Standalone binaries embed the full runtime and are fully self-contained.

---

## `devsper peer`

Start a peer node in the distributed cluster.

```bash
devsper peer [--listen <addr>] [--join <addr>]
```

| Flag               | Description                                          |
|--------------------|------------------------------------------------------|
| `--listen <addr>`  | Bind address for this node. Default: `0.0.0.0:7000`.|
| `--join <addr>`    | Coordinator address to join on startup.              |

**Examples:**

```bash
# Bootstrap a coordinator (no --join → becomes coordinator)
devsper peer --listen 0.0.0.0:7000

# Worker joins existing cluster
devsper peer --join 10.0.0.1:7000 --listen 0.0.0.0:7001

# Another worker
devsper peer --join 10.0.0.1:7000 --listen 0.0.0.0:7002
```

The first node without `--join` holds the coordinator role. On coordinator failure, workers elect a new leader via Raft-lite and resume from the last EventLog snapshot.

---

## `devsper inspect`

Attach to a running workflow and stream live events.

```bash
devsper inspect <run-id>
```

Connects to `/tmp/devsper-<run-id>.sock` and prints a JSON-RPC stream of `GraphEvent` messages. The TUI uses the same protocol.

**Example:**

```bash
# In one terminal
devsper run workflow.devsper --inspect-socket /tmp/devsper-abc123.sock

# In another terminal
devsper inspect abc123
```

---

## `devsper tui`

Launch the interactive terminal UI.

```bash
devsper tui [run-id]
```

Opens the Textual TUI with two tabs:
- **Events** — live stream of `GraphEvent` messages from the running workflow.
- **Agent Output** — raw LLM output per task.

If `run-id` is given, connects immediately to `/tmp/devsper-<run-id>.sock`. Otherwise shows the idle screen.

**Via Python:**

```bash
python -m devsper tui
# or with run-id
python -m devsper tui abc123
```

**Keyboard shortcuts:**

| Key | Action  |
|-----|---------|
| `q` | Quit    |
| `r` | Refresh |

---

## Environment variables

All flags have environment variable equivalents. See [Runtime Configuration](runtime-config.md).

---

## Global flags

| Flag      | Description              |
|-----------|--------------------------|
| `--help`  | Show help for any command.|
| `--version` | Print version and exit. |
