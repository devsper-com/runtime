# Writing Workflows

Workflows are `.devsper` files that define a directed acyclic graph of agent tasks. The graph can evolve at runtime — agents can inject, split, and prune nodes as they discover what work is needed.

---

## Pattern 1: Linear pipeline

Tasks run in sequence. Each task receives the prior task's result via the prompt template.

```lua
local devsper = require("devsper")

local wf = devsper.workflow({
    name  = "pipeline",
    model = "claude-opus-4-6",
})

wf.task("fetch", {
    prompt = "Fetch the README from {input.repo_url} and return its raw text.",
})

wf.task("summarize", {
    depends_on = {"fetch"},
    prompt     = "Summarize this README in 3 bullet points:\n\n{fetch.result}",
})

wf.task("classify", {
    depends_on = {"summarize"},
    prompt     = "Classify this project as: library, tool, framework, or other.\n\n{summarize.result}",
})

wf.input("repo_url", { type = "string", required = true })

return wf
```

---

## Pattern 2: Fan-out / fan-in

A planner task injects parallel subtasks at runtime. A summarizer waits for all of them with `depends_on = {"*"}`.

```lua
local wf = devsper.workflow({
    name       = "parallel-analysis",
    model      = "claude-opus-4-6",
    workers    = 8,
    evolution  = { allow_mutations = true },
})

wf.task("plan", {
    can_mutate = true,
    prompt = [[
Analyze this repository. Decompose the analysis into 4-6 parallel subtasks.
For each subtask, inject it as a new graph node using AddNode mutation.
Repository: {input.repo_url}
    ]],
})

wf.task("report", {
    depends_on = {"*"},   -- waits for all dynamically injected tasks
    prompt     = "Synthesize all findings into a structured report.",
})

wf.plugin("git", { source = "builtin:git" })
wf.input("repo_url", { type = "string", required = true })

return wf
```

The `"*"` wildcard in `depends_on` resolves to every node in the graph at execution time. The `report` task runs only after every injected subtask completes.

---

## Pattern 3: Self-mutating workflow

Agents with `can_mutate = true` can reshape the graph mid-run. This enables workflows that adapt to what they discover.

```lua
local wf = devsper.workflow({
    name      = "adaptive",
    model     = "claude-opus-4-6",
    evolution = {
        allow_mutations = true,
        max_depth       = 5,
    },
})

wf.task("triage", {
    can_mutate = true,
    prompt = [[
Examine the codebase at {input.path}.
If you find security issues, inject a "security-audit" task.
If the test coverage is low, inject a "write-tests" task.
Always inject a "final-summary" task that depends on everything.
    ]],
})

wf.plugin("filesystem", { source = "builtin:filesystem" })
wf.plugin("code",       { source = "builtin:code" })
wf.input("path", { type = "string", required = true })

return wf
```

The mutation API the agent uses is documented in [Graph Execution](../concepts/graph-execution.md).

---

## Pattern 4: Speculative execution

Mark tasks as speculative to prefetch LLM context while the graph is still running. If the prediction is wrong, discard them at no cost.

```lua
local wf = devsper.workflow({
    name      = "speculative",
    model     = "claude-opus-4-6",
    evolution = {
        allow_mutations = true,
        speculative     = true,
    },
})

wf.task("fetch", {
    can_mutate = true,
    prompt = [[
Fetch the document at {input.url}.
Mark the likely follow-up tasks as Speculative:
  - "extract-entities" if the doc contains structured data
  - "translate" if the doc is not in English
Confirm or discard them based on what you find.
    ]],
})

wf.input("url", { type = "string", required = true })

return wf
```

Speculative nodes run in parallel with their dependencies. If discarded, their results are dropped. If confirmed, they complete immediately — no waiting.

---

## Pattern 5: Conditional branching via Lua

Use Lua logic in the workflow definition to conditionally register tasks:

```lua
local wf = devsper.workflow({ name = "conditional", model = "claude-opus-4-6" })

local include_audit = os.getenv("RUN_AUDIT") == "true"

wf.task("analyze", {
    prompt = "Analyze the codebase at {input.path}.",
})

if include_audit then
    wf.task("audit", {
        depends_on = {"analyze"},
        prompt     = "Run a security audit on the findings from the analysis.",
    })
end

wf.task("report", {
    depends_on = include_audit and {"analyze", "audit"} or {"analyze"},
    prompt     = "Write a final report.",
})

wf.input("path", { type = "string", required = true })
return wf
```

Lua runs at compile time to build the static workflow graph. Runtime mutations handle the dynamic case.

---

## Using task results in prompts

Reference prior task outputs with `{task_name.result}`:

```lua
wf.task("summarize", {
    depends_on = {"fetch"},
    prompt     = "Summarize this text:\n\n{fetch.result}",
})
```

Reference inputs with `{input.name}`:

```lua
wf.task("analyze", {
    prompt = "Analyze {input.repo_url} with focus on {input.language}.",
})
```

---

## Model selection per task

Override the workflow model for specific tasks:

```lua
local wf = devsper.workflow({
    name  = "mixed-models",
    model = "gpt-4o",          -- default for all tasks
})

wf.task("plan", {
    model  = "claude-opus-4-6", -- use a more capable model for planning
    prompt = "Decompose this task...",
})

wf.task("execute", {
    -- inherits gpt-4o from workflow default
    prompt = "Execute the plan...",
})
```

---

## Full example: repository analysis

```lua
-- examples/analyze-repo.devsper
local devsper = require("devsper")

local wf = devsper.workflow({
    name    = "analyze-repo",
    model   = "claude-opus-4-6",
    workers = 6,
    evolution = {
        allow_mutations = true,
        max_depth       = 8,
        speculative     = true,
    },
})

wf.task("clone", {
    prompt = "Clone {input.repo_url} at branch {input.branch} to ./repo",
})

wf.task("plan", {
    depends_on = {"clone"},
    can_mutate = true,
    model      = "claude-opus-4-6",
    prompt     = [[
Examine the repository structure at ./repo.
Decompose the analysis into parallel subtasks covering:
architecture, dependencies, test coverage, security, and documentation.
Inject each as a separate task node.
    ]],
})

wf.task("report", {
    depends_on = {"*"},
    prompt     = "Synthesize all findings into a comprehensive analysis report.",
})

wf.plugin("git",        { source = "builtin:git" })
wf.plugin("filesystem", { source = "builtin:filesystem" })
wf.plugin("code",       { source = "builtin:code" })

wf.input("repo_url", { type = "string", required = true })
wf.input("branch",   { type = "string", default = "main" })

return wf
```

```bash
devsper run examples/analyze-repo.devsper \
  --input repo_url=https://github.com/example/repo \
  --input branch=main
```
