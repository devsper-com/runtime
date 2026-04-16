# Plugins

Plugins extend agent capabilities by exposing tools. A tool is a Lua function that agents can call via their LLM tool-use interface. The runtime wraps each tool in a JSON Schema descriptor so the LLM knows what arguments to pass.

---

## How plugins work

When a workflow loads a plugin, the runtime:

1. Reads the plugin's `.devsper` source file (or built-in registration)
2. Executes it in a Lua VM with the `devsper` stdlib injected
3. Collects all `devsper.tool(...)` registrations from `__devsper_tools__`
4. Converts each tool's `params` table to a JSON Schema `ToolDef`
5. Passes the `ToolDef` list to the LLM in every agent request

When the LLM emits a tool call, the runtime:

1. Finds the matching tool by name
2. Calls the Lua `run` function with `(ctx, args)`
3. Serializes the return value to JSON
4. Sends it back to the LLM as a `ToolResult`

---

## devsper Lua stdlib

The following functions and tables are available in all plugin and workflow files.

### devsper.tool(name, spec)

Register a tool. See [.devsper Format](devsper-format.md) for the full spec.

```lua
devsper.tool("my.tool", {
    description = "What this tool does",
    params = {
        input = { type = "string", required = true },
    },
    run = function(ctx, args)
        return { result = args.input:upper() }
    end,
})
```

### devsper.workflow(config)

Register a workflow (used in workflow files, not tool files). Returns a builder.

### devsper.exec(cmd, args)

Run an external process. Returns a table `{ code, stdout, stderr }`.

```lua
local r = devsper.exec("git", { "clone", "https://github.com/org/repo", "./repo" })
if r.code ~= 0 then
    return nil, "git clone failed: " .. r.stderr
end
return { path = "./repo" }
```

> `devsper.exec` is only available when the plugin is loaded with `allow_exec = true` (the default for built-in plugins). Sandboxed plugins that declare no `exec` capability will receive a runtime error if they call this function.

### devsper.http.get(url, opts)

Make an HTTP GET request.

```lua
local resp = devsper.http.get("https://api.example.com/data", {
    timeout = 30,
    headers = { ["Authorization"] = "Bearer " .. token },
})
if resp.status ~= 200 then
    return nil, "HTTP error: " .. resp.status
end
return { data = resp.body }
```

Returns `{ status, body, headers }`.

### devsper.http.post(url, body, opts)

Make an HTTP POST request.

```lua
local resp = devsper.http.post("https://api.example.com/items",
    '{"name": "foo"}',
    { headers = { ["Content-Type"] = "application/json" } }
)
```

Returns `{ status, body, headers }`.

### devsper.log(level, msg)

Emit a structured log line. Valid levels: `"debug"`, `"info"`, `"warn"`, `"error"`.

```lua
devsper.log("info", "Cloning repository: " .. url)
devsper.log("error", "Unexpected response code: " .. tostring(code))
```

Logs are routed through `tracing` and tagged with `plugin = true`.

### devsper.ctx

Read-only context table, populated by the runtime before each tool call.

| Field | Type | Description |
|---|---|---|
| `devsper.ctx.run_id` | string | Current run's UUID |
| `devsper.ctx.workspace` | string | Absolute path to the run's working directory |
| `devsper.ctx.task_id` | string | Current task node ID |
| `devsper.ctx.node_id` | string | Same as `task_id` (alias) |

```lua
devsper.log("info", "Running in workspace: " .. devsper.ctx.workspace)
```

---

## Sandbox rules

Each plugin Lua VM is isolated from other plugins and the host filesystem via:

- **Path restriction**: `devsper.exec` always runs with `current_dir` set to `devsper.ctx.workspace`. Absolute paths outside the workspace are not blocked at the Lua level but are subject to OS permissions.
- **Capability declarations**: a plugin can declare what capabilities it needs. If `allow_exec` is false (sandbox mode), calling `devsper.exec` raises a `RuntimeError`.
- **No `require` of arbitrary system modules**: the Lua VM does not load standard OS/io/socket libraries by default. The `devsper` table is the sole bridge to the host.

---

## External process mode

For tools that need languages other than Lua (Python, Node, shell scripts), use `devsper.exec` to call an external process that speaks JSON over stdio:

```lua
devsper.tool("python.analyze", {
    description = "Run Python static analysis",
    params = {
        path = { type = "string", required = true },
    },
    run = function(ctx, args)
        local input = '{"path":"' .. args.path .. '"}'
        local r = devsper.exec("python3", { "./tools/analyze.py", input })
        if r.code ~= 0 then
            return nil, r.stderr
        end
        -- parse JSON output
        return { output = r.stdout }
    end,
})
```

The child process receives arguments and writes JSON results to stdout.

---

## Built-in plugins

### git (`builtin:git`)

Tools for interacting with git repositories.

| Tool | Description | Key params |
|---|---|---|
| `git.clone` | Clone a repository | `url`, `path` |
| `git.diff` | Show diff | `path`, `staged` |
| `git.log` | Show commit log | `path`, `n` |
| `git.status` | Show working tree status | `path` |

### filesystem (`builtin:filesystem`)

Tools for reading and writing files.

| Tool | Description | Key params |
|---|---|---|
| `fs.read` | Read file contents | `path` |
| `fs.write` | Write file | `path`, `content` |
| `fs.list` | List directory | `path` |
| `fs.exists` | Check if path exists | `path` |

### http (`builtin:http`)

HTTP client tools.

| Tool | Description | Key params |
|---|---|---|
| `http.get` | GET request | `url`, `timeout`, `headers` |
| `http.post` | POST request | `url`, `body`, `headers` |

### search (`builtin:search`)

Web and local search tools.

| Tool | Description | Key params |
|---|---|---|
| `search.web` | Web search | `query`, `n` |
| `search.local` | Search files in workspace | `pattern`, `path` |

### code (`builtin:code`)

Code analysis tools.

| Tool | Description | Key params |
|---|---|---|
| `code.run` | Execute code in a sandbox | `language`, `code` |
| `code.lint` | Lint source file | `path`, `language` |

---

## Loading plugins in a workflow

```lua
-- Load a built-in plugin
wf.plugin("git", { source = "builtin:git" })

-- Load a local .devsper tool file
wf.plugin("my-scraper", { source = "./tools/scraper.devsper" })

-- Load with an absolute path
wf.plugin("analytics", { source = "/shared/tools/analytics.devsper" })
```

The `name` passed to `wf.plugin()` is used as the plugin's namespace in log output and error messages. The tool names themselves (e.g., `git.clone`) come from the `devsper.tool()` registrations inside the plugin file.
