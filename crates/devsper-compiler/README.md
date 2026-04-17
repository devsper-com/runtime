# devsper-compiler

Workflow compiler and loader for the devsper runtime. Parses `.devsper` workflow files into an intermediate representation (IR) and can emit compiled `.devsper.bin` bytecode (JSON IR).

## Workflow format

`.devsper` files are **Lua** scripts that call the `devsper` DSL:

```lua
local devsper = devsper

local wf = devsper.workflow({
    name    = "research-agent",
    model   = "claude-sonnet-4-6",
    workers = 4,
    bus     = "memory",
    evolution = {
        allow_mutations = true,
        max_depth       = 10,
        speculative     = false,
    },
})

wf.input("topic", { type = "string", required = true })

wf.task("search", {
    prompt     = "Search for recent papers on the topic provided.",
    depends_on = {},
})

wf.task("summarize", {
    prompt     = "Summarize the search results into an executive summary.",
    depends_on = { "search" },
})

wf.plugin("web-search", { source = "builtin:search" })

return wf
```

## Intermediate Representation

`WorkflowIr` is the compiled form — a plain Rust struct you can serialize to JSON, persist, or feed directly into the executor:

```rust
pub struct WorkflowIr {
    pub name: String,
    pub model: String,
    pub workers: usize,
    pub tasks: Vec<TaskIr>,     // { id, prompt, depends_on, ... }
    pub plugins: Vec<PluginRef>,
    pub inputs: HashMap<String, InputIr>,
}
```

## Usage

```toml
[dependencies]
devsper-compiler = "0.1"
```

```rust
use devsper_compiler::WorkflowLoader;
use std::path::Path;

// Load source or compiled bytecode (auto-detected by extension)
let ir = WorkflowLoader::load(Path::new("my_workflow.devsper"))?;
println!("Loaded '{}' with {} tasks", ir.name, ir.tasks.len());

// Compile to bytecode
use devsper_compiler::{Compiler, CompileOptions};
let compiler = Compiler::new(CompileOptions::default());
let ir = compiler.parse_file(Path::new("my_workflow.devsper"))?;
let bytes = serde_json::to_vec(&ir)?;
std::fs::write("my_workflow.devsper.bin", bytes)?;
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
