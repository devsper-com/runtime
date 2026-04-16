# Compiler

The devsper compiler transforms `.devsper` workflow files into executable form. Three output modes exist: interpret-in-place, bytecode (`.devsper.bin`), and standalone binary (`--embed`).

---

## Pipeline overview

```
.devsper file
    │
    ▼
Lua 5.4 VM (mlua, vendored)
  + inject_compiler_stdlib()      ← no-op stubs + IR-capturing devsper API
    │
    ▼
Execute Lua source
  → populates globals:
      __workflow__  { name, model, workers, bus, evolution }
      __tasks__     [ { name, prompt, depends_on, model, can_mutate } ]
      __plugins__   [ { name, source, unsafe } ]
      __inputs__    [ { name, type, required, default } ]
    │
    ▼
extract_ir()
  → WorkflowIr { workflow, tasks, plugins, inputs }
    │
    ├──► JSON serialize → .devsper.bin  (bytecode mode)
    │
    └──► Rust codegen → cargo build → standalone binary  (--embed mode)
```

---

## `inject_compiler_stdlib()`

The compiler injects a modified version of the devsper Lua stdlib. Instead of executing tools or making HTTP calls, the stubs capture what the workflow declares:

```lua
-- injected at compile time
devsper = {}

devsper.workflow = function(config)
    __workflow__ = config
    local builder = {}
    builder.task = function(name, spec)
        table.insert(__tasks__, { name = name, spec = spec })
    end
    builder.plugin = function(name, spec)
        table.insert(__plugins__, { name = name, spec = spec })
    end
    builder.input = function(name, spec)
        table.insert(__inputs__, { name = name, spec = spec })
    end
    return builder
end

-- exec, http, log are no-ops at compile time
devsper.exec = function() return { code = 0, stdout = "", stderr = "" } end
devsper.log  = function() end
```

This means the Lua source executes safely at compile time even if it references external tools or paths that don't exist yet.

---

## `WorkflowIr`

The intermediate representation captures everything needed to reconstruct the graph:

```rust
pub struct WorkflowIr {
    pub workflow: WorkflowConfig,
    pub tasks:    Vec<TaskIr>,
    pub plugins:  Vec<PluginIr>,
    pub inputs:   Vec<InputIr>,
}

pub struct TaskIr {
    pub name:       String,
    pub prompt:     String,
    pub model:      Option<String>,
    pub depends_on: Vec<String>,
    pub can_mutate: bool,
}
```

---

## Bytecode mode

```bash
devsper compile workflow.devsper
# Produces workflow.devsper.bin
```

The `WorkflowIr` is serialized to JSON and written to `.devsper.bin`. At runtime, `devsper run workflow.devsper.bin` loads the JSON, deserializes the IR, builds the `NodeSpec` list, and starts the `GraphActor` — no Lua VM needed.

Bytecode is portable across machines running the same devsper version. It is not a binary format — it is human-readable JSON wrapped in a version envelope:

```json
{
  "version": "1",
  "ir": { "workflow": { ... }, "tasks": [ ... ], ... }
}
```

---

## Standalone binary mode

```bash
devsper compile --embed workflow.devsper
# Produces ./workflow
```

The compiler:
1. Extracts the `WorkflowIr` as above.
2. Generates a small Rust `main.rs` that embeds the IR as a `const &str`.
3. Runs `cargo build --release` on a temporary crate that depends on `devsper-bin`.
4. Copies the resulting binary to the output path.

The standalone binary is fully self-contained. It accepts the same `--input` flags as `devsper run`:

```bash
./workflow --input repo_url=https://github.com/example/repo
```

No devsper installation required on the target machine. No PATH dependencies.

---

## Validation

The compiler validates the `WorkflowIr` before emitting output:

| Check                     | Error                                                    |
|---------------------------|----------------------------------------------------------|
| Circular `depends_on`     | `"cycle detected: task A → B → A"`                     |
| Unknown `depends_on` ref  | `"task 'report' depends on unknown task 'missing'"`      |
| Missing required inputs   | `"required input 'repo_url' not declared"`               |
| Empty prompt              | `"task 'fetch' has an empty prompt"`                     |

Validation errors are printed with source context and exit code 1.

---

## Runtime loading

The `WorkflowLoader` in `devsper-compiler` handles both file types transparently:

```rust
let ir = WorkflowLoader::load("workflow.devsper")?;     // executes Lua
let ir = WorkflowLoader::load("workflow.devsper.bin")?; // parses JSON
```

The `devsper-bin` `run_command` uses `WorkflowLoader`, so `devsper run` accepts either format with no flags needed.

---

## `.devsper` grammar

`.devsper` files are valid Lua 5.4 with `devsper` as a pre-loaded global. There are no custom keywords or syntax extensions — any Lua 5.4 tooling (syntax highlighting, formatters, linters) works directly.

The `devsper` table is the only injected symbol. Everything else is standard Lua:

```lua
-- Valid: use loops, conditionals, functions
local tasks = {"lint", "test", "build"}
for _, name in ipairs(tasks) do
    wf.task(name, { prompt = "Run " .. name .. " on the codebase." })
end

-- Valid: read environment for feature flags
if os.getenv("INCLUDE_PERF") then
    wf.task("perf", { prompt = "Run performance benchmarks." })
end
```
