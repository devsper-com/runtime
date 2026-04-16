# .devsper Format

`.devsper` files are **Lua 5.4 scripts** with the `devsper` global injected by the runtime. They describe workflows and tools declaratively, but with the full power of Lua available for conditional logic, loops, and string manipulation.

---

## Two file types

### workflow.devsper

Defines a workflow — a named set of tasks, plugins, and inputs.

```lua
local wf = devsper.workflow({ ... })
wf.task(...)
wf.plugin(...)
wf.input(...)
return wf
```

### tool.devsper

Defines one or more tools that can be loaded into a workflow as a plugin.

```lua
devsper.tool("tool-name", {
    description = "...",
    params = { ... },
    run = function(ctx, args) ... end,
})
```

---

## Workflow syntax

### devsper.workflow(config)

Creates a workflow builder. Call at the top of the file and assign the result.

```lua
local wf = devsper.workflow({
    name    = "my-workflow",     -- required: display name
    model   = "claude-sonnet-4-6", -- default model for all tasks
    workers = 4,                 -- concurrent executor threads
    bus     = "memory",          -- "memory" | "redis" | "kafka"
    evolution = {
        allow_mutations = true,  -- agents may emit GraphMutation
        max_depth       = 10,    -- max mutation depth per branch
        speculative     = false, -- enable speculative execution
    },
})
```

Returns a workflow builder object with `.task()`, `.plugin()`, and `.input()` methods.

### wf.task(id, spec)

Adds a task node to the workflow DAG.

```lua
wf.task("fetch-data", {
    prompt     = "Fetch data from the API and return the raw JSON.",
    model      = "claude-haiku-3-5",  -- optional: overrides workflow default
    can_mutate = false,               -- can this task emit GraphMutation?
    depends_on = {},                  -- list of task IDs this depends on
})
```

**Fields:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | string | yes | — | The instruction sent to the LLM agent |
| `model` | string | no | workflow default | Override model for this task |
| `can_mutate` | boolean | no | `false` | Allow agent to emit mutations |
| `depends_on` | string[] | no | `{}` | Task IDs that must complete first |

**Wildcard dependency** — depend on all other nodes (including dynamically added ones):

```lua
wf.task("final-report", {
    prompt     = "Synthesize all findings into a final report.",
    depends_on = { "*" },   -- waits for every other completed node
})
```

### wf.plugin(name, spec)

Loads a plugin (tool bundle) into the workflow. Agents can call the tools via their LLM tool-use interface.

```lua
wf.plugin("git", { source = "builtin:git" })         -- built-in plugin
wf.plugin("search", { source = "builtin:search" })
wf.plugin("my-tool", { source = "./tools/scraper.devsper" })  -- local file
```

**Fields:**

| Field | Type | Description |
|---|---|---|
| `source` | string | `builtin:<name>` or path to a `.devsper` tool file |

### wf.input(name, spec)

Declares a runtime input variable. Inputs are substituted into task prompts using `{{name}}` syntax.

```lua
wf.input("repo_url", { type = "string", required = true })
wf.input("branch",   { type = "string", default = "main" })
wf.input("depth",    { type = "number", default = 5 })
```

**Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | no | `"string"` | `"string"`, `"number"`, `"boolean"` |
| `required` | boolean | no | `false` | Fail if not provided at runtime |
| `default` | any | no | `nil` | Value used when not provided |

Pass inputs at runtime:

```bash
devsper run workflow.devsper --input repo_url=https://github.com/... --input branch=feature/x
```

---

## Tool syntax

### devsper.tool(name, spec)

Registers a tool. Call once per tool per file; multiple tools can be defined in a single `.devsper` file.

```lua
devsper.tool("http.get", {
    description = "Fetch a URL and return the response body",
    params = {
        url     = { type = "string",  required = true },
        timeout = { type = "number",  default = 30 },
        headers = { type = "object",  required = false },
    },
    run = function(ctx, args)
        local resp = devsper.http.get(args.url, { timeout = args.timeout })
        if resp.status ~= 200 then
            return nil, "HTTP " .. resp.status
        end
        return { body = resp.body, status = resp.status }
    end,
})
```

**Spec fields:**

| Field | Type | Description |
|---|---|---|
| `description` | string | Shown to the LLM agent as the tool description |
| `params` | table | Parameter schema (see below) |
| `run` | function | Implementation: `function(ctx, args) → result, error?` |

**Parameter schema:** each key is a parameter name with `type`, `required`, `default` subfields.

| Type value | Lua type | JSON Schema mapping |
|---|---|---|
| `"string"` | string | `type: string` |
| `"number"` | number | `type: number` |
| `"boolean"` | boolean | `type: boolean` |
| `"object"` | table | `type: object` |
| `"array"` | table (sequence) | `type: array` |

**Return convention:**

- Success: return a table (serialized to JSON and passed back to the LLM)
- Error: return `nil, "error message"` (the error is surfaced to the agent)

---

## Depends-on patterns

Linear chain:

```lua
wf.task("a", { prompt = "...", depends_on = {} })
wf.task("b", { prompt = "...", depends_on = { "a" } })
wf.task("c", { prompt = "...", depends_on = { "b" } })
```

Fan-out (parallel tasks, then merge):

```lua
wf.task("planner",  { prompt = "...", depends_on = {} })
wf.task("worker-1", { prompt = "...", depends_on = { "planner" } })
wf.task("worker-2", { prompt = "...", depends_on = { "planner" } })
wf.task("merge",    { prompt = "...", depends_on = { "worker-1", "worker-2" } })
```

Wait for everything (including dynamically added nodes):

```lua
wf.task("summarize", {
    prompt     = "Write a final summary of all results.",
    depends_on = { "*" },
})
```

---

## Conditional logic with Lua

Because `.devsper` files are plain Lua, you can use conditionals and loops to build the DAG programmatically:

```lua
local wf = devsper.workflow({ name = "dynamic", model = "claude-sonnet-4-6" })

local targets = { "auth", "payments", "search" }

for i, module in ipairs(targets) do
    wf.task("analyze-" .. module, {
        prompt     = "Analyze the " .. module .. " module for security issues.",
        depends_on = {},
    })
end

wf.task("report", {
    prompt     = "Combine all module security analyses into one report.",
    depends_on = { "*" },
})

return wf
```

---

## Compilation pipeline

A `.devsper` file goes through this pipeline:

```
.devsper (Lua source)
    │
    ├── inject_compiler_stdlib()
    │       installs no-op stubs for devsper.exec, devsper.log
    │       installs IR-capturing devsper.workflow(), wf.task(), etc.
    │
    ├── lua.load(source).exec()
    │       evaluates the Lua; workflow/task/plugin/input calls
    │       populate __workflow__, __tasks__, __plugins__, __inputs__ globals
    │
    ├── extract_ir()
    │       reads the globals → WorkflowIr struct
    │
    └── serde_json::to_vec_pretty(&ir)
            → .devsper.bin  (portable JSON IR)
```

The `.devsper.bin` file is plain JSON. You can inspect it:

```bash
cat workflow.devsper.bin | jq .
```

At runtime, `WorkflowLoader::load()` accepts both `.devsper` (parses on the fly) and `.devsper.bin` (JSON parse only — faster, no mlua overhead).

---

## Example: complete workflow file

```lua
-- code-review.devsper
-- Automated code review workflow using git and filesystem tools.

local wf = devsper.workflow({
    name    = "code-review",
    model   = "claude-sonnet-4-6",
    workers = 3,
    bus     = "memory",
    evolution = {
        allow_mutations = true,
        max_depth       = 8,
        speculative     = false,
    },
})

wf.plugin("git", { source = "builtin:git" })
wf.plugin("fs",  { source = "builtin:filesystem" })

wf.input("repo_path", { type = "string", required = true })
wf.input("focus",     { type = "string", default = "all" })

wf.task("diff", {
    prompt     = "Use git.diff to get the staged diff in {{repo_path}}. "
                 .. "Return the diff text.",
    depends_on = {},
})

wf.task("review", {
    prompt     = "Review the diff for bugs, security issues, and code quality. "
                 .. "Focus area: {{focus}}. "
                 .. "If you find complex issues that warrant separate investigation, "
                 .. "add sub-tasks via mutations.",
    can_mutate = true,
    depends_on = { "diff" },
})

wf.task("report", {
    prompt     = "Write a final review report with a summary, findings, "
                 .. "and actionable recommendations.",
    depends_on = { "*" },
})

return wf
```
