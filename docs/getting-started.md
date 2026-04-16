# Getting Started

Devsper is a self-evolving AI workflow engine. You define workflows in a Lua-based `.devsper` format, and the runtime executes them as a dynamic directed acyclic graph (DAG) of AI agent tasks. Nodes can mutate the graph at runtime — adding, splitting, or pruning tasks based on what each agent discovers.

---

## Installation

### Via pip (Python wrapper + bundled binary)

```bash
pip install devsper
```

This installs the `devsper` CLI entry point. On first use it finds the bundled Rust binary or falls back to a `cargo build` output if you're developing locally.

To also get the interactive TUI:

```bash
pip install 'devsper[tui]'
```

### Build from source (Rust)

Requires Rust 1.78+ and Cargo.

```bash
git clone https://github.com/devsper-io/devsper
cd devsper/runtime
cargo build --release -p devsper-bin
# binary at: target/release/devsper
```

Add to PATH:

```bash
export PATH="$PWD/target/release:$PATH"
```

---

## Your first workflow

Create a file called `summarize.devsper`:

```lua
-- summarize.devsper
-- A simple two-task pipeline: fetch content, then summarize it.

local wf = devsper.workflow({
    name    = "summarize",
    model   = "claude-sonnet-4-6",
    workers = 2,
    bus     = "memory",
    evolution = {
        allow_mutations = false,
        max_depth       = 5,
        speculative     = false,
    },
})

wf.input("topic", { type = "string", required = true })

wf.task("research", {
    prompt     = "Research the topic: {{topic}}. Gather key facts and findings.",
    can_mutate = false,
    depends_on = {},
})

wf.task("summarize", {
    prompt     = "Summarize the research findings into a concise 3-paragraph report.",
    depends_on = { "research" },
})

return wf
```

Run it:

```bash
devsper run summarize.devsper --input topic="quantum computing"
```

The runtime will:
1. Load and validate the workflow
2. Build a DAG: `research` → `summarize`
3. Execute `research` (it has no dependencies)
4. Once `research` completes, execute `summarize`
5. Print results and exit

---

## Compile to bytecode

Compiling validates the workflow and serializes it to a portable `.devsper.bin` JSON IR file:

```bash
devsper compile summarize.devsper
# Writes: summarize.devsper.bin
```

Run from bytecode (same flags, identical behavior):

```bash
devsper run summarize.devsper.bin --input topic="quantum computing"
```

---

## Compile to a standalone binary

The `--embed` flag bundles the workflow IR into a self-contained executable. No separate `.devsper` file is needed at runtime.

```bash
devsper compile summarize.devsper --embed --output ./summarize
chmod +x ./summarize
./summarize --input topic="quantum computing"
```

> Note: `--embed` requires Rust toolchain on the build machine. The resulting binary does not.

---

## A self-mutating workflow

This example shows a planner agent that dynamically adds tasks during execution:

```lua
-- plan-and-execute.devsper

local wf = devsper.workflow({
    name    = "plan-and-execute",
    model   = "claude-sonnet-4-6",
    workers = 4,
    bus     = "memory",
    evolution = {
        allow_mutations = true,
        max_depth       = 10,
        speculative     = false,
    },
})

wf.input("goal", { type = "string", required = true })

-- The planner has can_mutate = true, so it can add new nodes
wf.task("planner", {
    prompt     = "Break down this goal into 3-5 concrete subtasks: {{goal}}. "
                 .. "For each subtask, emit an AddNode mutation with a clear prompt.",
    can_mutate = true,
    depends_on = {},
})

-- The summarizer waits for ALL nodes to complete (wildcard dependency)
wf.task("summarize", {
    prompt     = "Collect all subtask results and write a final report.",
    depends_on = { "*" },
})

return wf
```

Run:

```bash
devsper run plan-and-execute.devsper --input goal="Build a REST API for a todo app"
```

The planner agent will emit `GraphMutation::AddNode` calls, injecting subtasks into the DAG. The summarizer waits until every node (including dynamically added ones) completes.

---

## Using plugins

Plugins expose tools to your agents. Load built-in plugins with `wf.plugin()`:

```lua
local wf = devsper.workflow({
    name    = "code-reviewer",
    model   = "claude-sonnet-4-6",
    workers = 2,
    bus     = "memory",
})

wf.plugin("git", { source = "builtin:git" })
wf.plugin("fs",  { source = "builtin:filesystem" })

wf.input("repo_path", { type = "string", required = true })

wf.task("review", {
    prompt = "Use the git.diff tool to get the staged diff in {{repo_path}}, "
             .. "then review the changes for bugs and code quality issues.",
    depends_on = {},
})

return wf
```

Available built-in plugins: `git`, `filesystem`, `http`, `search`, `code`.

---

## Environment variables

Set your LLM provider key before running:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # for claude-* models
export OPENAI_API_KEY=sk-...           # for gpt-* models
export ZAI_API_KEY=...                 # for zai:/glm-* models
```

Devsper automatically detects which providers are available and routes to them based on the model name prefix.

---

## Next steps

- [Concepts: Graph Execution](concepts/graph-execution.md) — how the DAG engine works
- [Concepts: .devsper Format](concepts/devsper-format.md) — full DSL reference
- [Reference: CLI](reference/cli.md) — all commands and flags
- [Reference: Stdlib](reference/stdlib.md) — the full Lua API
- [Guides: Writing Workflows](guides/writing-workflows.md) — patterns and examples
