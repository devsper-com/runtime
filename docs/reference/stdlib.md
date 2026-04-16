# Lua Stdlib Reference

Every `.devsper` file runs inside a sandboxed Lua 5.4 VM with the `devsper` global table pre-populated. Standard Lua `os`, `io`, and `package` modules are not available unless the plugin declares `unsafe = true`.

---

## `devsper.workflow(config)`

Define a workflow. Returns a workflow builder object.

```lua
local wf = devsper.workflow({
    name    = "my-workflow",      -- string, required
    model   = "claude-opus-4-6",  -- default model for all tasks
    workers = 4,                  -- concurrent task limit (default: 4)
    bus     = "memory",           -- "memory" | "redis" | "kafka"
    evolution = {
        allow_mutations = true,   -- agents may mutate the graph
        max_depth       = 10,     -- max mutation nesting depth
        speculative     = true,   -- enable speculative execution
    },
})
```

### `wf.task(name, spec)`

Register a task node.

```lua
wf.task("plan", {
    prompt     = "Decompose the analysis into parallel subtasks.",
    model      = "claude-opus-4-6",  -- overrides workflow default
    depends_on = {"fetch"},           -- list of task names, or {"*"} for all
    can_mutate = true,                -- this task may inject GraphMutations
})
```

| Field        | Type     | Description                                               |
|--------------|----------|-----------------------------------------------------------|
| `prompt`     | string   | Prompt template. Use `{task_name.result}` for prior results. |
| `model`      | string   | LLM model name. Inherits workflow default if omitted.     |
| `depends_on` | string[] | Upstream task names. `{"*"}` waits for all prior tasks.  |
| `can_mutate` | bool     | Allow this task to return `GraphMutation` requests.       |

### `wf.plugin(name, spec)`

Load a plugin (tool set) into the workflow.

```lua
wf.plugin("git",    { source = "builtin:git" })
wf.plugin("search", { source = "./plugins/search.devsper" })
wf.plugin("myapi",  { source = "./tools/myapi.devsper", unsafe = true })
```

| Field    | Type   | Description                                      |
|----------|--------|--------------------------------------------------|
| `source` | string | `"builtin:<name>"` or path to a `.devsper` file. |
| `unsafe` | bool   | Allow raw `os`/`io` access in this plugin.       |

### `wf.input(name, spec)`

Declare a required or optional workflow input.

```lua
wf.input("repo_url", { type = "string", required = true })
wf.input("branch",   { type = "string", default = "main" })
wf.input("depth",    { type = "number", default = 3 })
```

Inputs are available in prompts as `{input.name}`.

---

## `devsper.tool(name, spec)`

Register a tool. Used inside plugin files.

```lua
devsper.tool("git.clone", {
    description = "Clone a git repository to a local path.",
    params = {
        url  = { type = "string", required = true },
        path = { type = "string", default = "./repo" },
    },
    run = function(ctx, args)
        local r = devsper.exec("git", {"clone", args.url, args.path})
        return { success = r.code == 0, path = args.path, output = r.stdout }
    end,
})
```

| Field         | Type     | Description                                       |
|---------------|----------|---------------------------------------------------|
| `description` | string   | Shown to the LLM in the tool manifest.            |
| `params`      | table    | Parameter schema. Each key maps to a param spec.  |
| `run`         | function | `function(ctx, args) → table`                     |

### Param spec fields

| Field      | Type   | Description                          |
|------------|--------|--------------------------------------|
| `type`     | string | `"string"` \| `"number"` \| `"bool"` |
| `required` | bool   | Error if missing from call.          |
| `default`  | any    | Value used when param is absent.     |

### `ctx` object

| Field       | Type   | Description                  |
|-------------|--------|------------------------------|
| `ctx.run_id`   | string | Current run's UUID.          |
| `ctx.task_id`  | string | Current task's UUID.         |
| `ctx.node_id`  | string | Current node's UUID.         |
| `ctx.workspace`| string | Workspace directory path.    |

---

## `devsper.exec(cmd, args)`

Run a subprocess. Restricted to workspace path unless `unsafe = true`.

```lua
local r = devsper.exec("git", {"clone", "https://github.com/example/repo", "./repo"})
-- r.code   → exit code (number)
-- r.stdout → captured stdout (string)
-- r.stderr → captured stderr (string)
```

Raises a Lua error if the command is not found or the path is outside the workspace sandbox.

---

## `devsper.http`

### `devsper.http.get(url, opts)`

```lua
local r = devsper.http.get("https://api.example.com/data", {
    headers = { Authorization = "Bearer " .. token },
    timeout = 10,   -- seconds
})
-- r.status  → HTTP status code (number)
-- r.body    → response body (string)
-- r.headers → response headers (table)
```

### `devsper.http.post(url, body, opts)`

```lua
local r = devsper.http.post("https://api.example.com/submit", {
    payload = "hello",
}, {
    headers = { ["Content-Type"] = "application/json" },
})
```

---

## `devsper.log(level, msg)`

Emit a structured log line. Appears in the TUI event log and `RUST_LOG` output.

```lua
devsper.log("info",  "Cloning repository...")
devsper.log("warn",  "Rate limit approaching")
devsper.log("error", "Failed to fetch: " .. err)
devsper.log("debug", "Response body: " .. r.body)
```

Levels: `"debug"` | `"info"` | `"warn"` | `"error"`
