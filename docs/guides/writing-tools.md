# Writing Tools

Tools extend what agents can do: file I/O, HTTP calls, subprocess execution, database queries — anything callable from Lua.

---

## Anatomy of a tool file

A tool file is a `.devsper` file that calls `devsper.tool()` one or more times:

```
tools/
└── websearch.devsper
```

```lua
-- tools/websearch.devsper
local devsper = require("devsper")

devsper.tool("web.search", {
    description = "Search the web and return the top result snippets.",
    params = {
        query   = { type = "string", required = true },
        results = { type = "number", default = 5 },
    },
    run = function(ctx, args)
        local r = devsper.http.get("https://api.search.example.com/search", {
            headers = { ["X-Api-Key"] = os.getenv("SEARCH_API_KEY") },
            query   = { q = args.query, n = tostring(args.results) },
        })
        if r.status ~= 200 then
            error("search failed: " .. r.status)
        end
        return { snippets = r.body }
    end,
})
```

---

## Step 1 — Define the param schema

Each param has three optional fields:

```lua
params = {
    url     = { type = "string", required = true  },
    timeout = { type = "number", default = 30     },
    verify  = { type = "bool",   default = true   },
}
```

The schema is exposed to the LLM as a tool manifest. Clear `description` fields help the model call tools correctly.

---

## Step 2 — Implement `run`

The `run` function receives a context object and the validated args:

```lua
run = function(ctx, args)
    devsper.log("info", "Searching for: " .. args.query)

    local r = devsper.http.get("https://...", {
        headers = { Authorization = "Bearer " .. ctx.run_id },
    })

    return { result = r.body, status = r.status }
end
```

Return a Lua table. It will be serialized to JSON and given back to the agent as the tool result.

Raise a Lua `error()` for failures — the runtime will capture it and return an error result to the agent.

---

## Step 3 — Use subprocess execution

For CLI-based tools, use `devsper.exec()`:

```lua
devsper.tool("git.log", {
    description = "Get recent git commits for a repository.",
    params = {
        path  = { type = "string", required = true },
        limit = { type = "number", default = 10 },
    },
    run = function(ctx, args)
        local r = devsper.exec("git", {
            "-C", args.path,
            "log", "--oneline",
            "-" .. tostring(args.limit),
        })
        if r.code ~= 0 then
            error("git log failed: " .. r.stderr)
        end
        return { commits = r.stdout }
    end,
})
```

`devsper.exec()` is sandboxed to the workspace directory by default. Paths outside the workspace raise an error unless the plugin is loaded with `unsafe = true`.

---

## Step 4 — Load the tool in a workflow

```lua
-- workflow.devsper
local devsper = require("devsper")

local wf = devsper.workflow({
    name  = "research",
    model = "claude-opus-4-6",
})

-- Load your tool file
wf.plugin("search",   { source = "./tools/websearch.devsper" })
wf.plugin("git",      { source = "builtin:git" })

wf.task("gather", {
    prompt = "Search for recent papers on {input.topic} and summarize findings.",
    -- Tools are available to the agent automatically
})

wf.input("topic", { type = "string", required = true })

return wf
```

---

## Multiple tools in one file

A single `.devsper` file can register any number of tools:

```lua
devsper.tool("fs.read",   { ... })
devsper.tool("fs.write",  { ... })
devsper.tool("fs.list",   { ... })
devsper.tool("fs.delete", { ... })
```

---

## External process mode

For tools requiring non-Lua runtimes (Python, Node.js, Go), use the external process escape hatch. The runtime forks the process and communicates over JSON stdio.

```lua
devsper.tool("python.analysis", {
    description = "Run a Python data analysis script.",
    mode = "process",
    command = {"python3", "./tools/analyze.py"},
    params = {
        dataset = { type = "string", required = true },
    },
})
```

The subprocess receives a JSON object on stdin and must write a JSON object to stdout:

```python
# tools/analyze.py
import json, sys

args = json.loads(sys.stdin.read())
result = {"summary": f"Analyzed {args['dataset']}"}
print(json.dumps(result))
```

---

## Sandbox capabilities

By default tools run with:
- Filesystem access limited to workspace directory
- No raw `os`, `io`, `package` Lua modules
- HTTP allowed to any URL
- Subprocess allowed to workspace-relative paths

Declare `unsafe = true` in `wf.plugin()` to remove sandbox restrictions for a specific plugin. Use only for trusted, audited tools.

---

## Built-in tools

Load any of the bundled plugins with `builtin:` prefix:

| Name         | Source                  | Tools                                       |
|--------------|-------------------------|---------------------------------------------|
| `git`        | `builtin:git`           | `git.clone`, `git.diff`, `git.log`          |
| `filesystem` | `builtin:filesystem`    | `fs.read`, `fs.write`, `fs.list`, `fs.stat` |
| `http`       | `builtin:http`          | `http.get`, `http.post`                     |
| `search`     | `builtin:search`        | `search.web`, `search.docs`                 |
| `code`       | `builtin:code`          | `code.run`, `code.lint`, `code.format`      |
