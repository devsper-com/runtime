# devsper-plugins

Lua 5.4 plugin runtime for the devsper workflow engine. Plugins are `.lua` files that expose tool functions callable by agents.

## How plugins work

1. A `.devsper` workflow declares `plugins = ["path/to/tool.lua"]`
2. `devsper-compiler` loads them via `WorkflowLoader`
3. `PluginRuntime` executes Lua functions with sandboxed I/O
4. Results are returned as `serde_json::Value`

## Plugin sandbox

Plugins run inside a restricted Lua environment:
- No `os.execute`, `io.popen`, or `require` for native modules
- Standard library: `string`, `table`, `math`, `json` (injected)
- Async-aware: Lua coroutines map onto Tokio tasks

## Usage

```toml
[dependencies]
devsper-plugins = "0.1"
# Lua 5.4 is vendored by default (no system Lua needed):
# devsper-plugins = { version = "0.1", features = ["lua-vendored"] }
```

```rust
use devsper_plugins::{PluginRegistry, PluginRuntime};

let registry = PluginRegistry::new();
registry.load_file("tools/search.lua").await?;

let runtime = PluginRuntime::new(registry);
let result = runtime.call("search", serde_json::json!({ "query": "rust async" })).await?;
```

### Example plugin (`tools/search.lua`)

```lua
function search(args)
  -- args is a Lua table decoded from JSON
  local query = args.query
  return { results = { "result1", "result2" } }
end
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
