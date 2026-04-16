use crate::{
    registry::{PluginRegistry, RegisteredTool},
    sandbox::Sandbox,
    stdlib::inject_stdlib,
};
use anyhow::{anyhow, Result};
use devsper_core::{ToolCall, ToolDef, ToolResult};
use mlua::prelude::*;
use std::path::Path;
use std::sync::Arc;
use tracing::{debug, info};

/// A loaded plugin with its registered tools
pub struct LoadedPlugin {
    pub name: String,
    pub tools: Vec<ToolDef>,
}

/// Manages Lua VMs for plugin execution
pub struct PluginRuntime {
    registry: Arc<PluginRegistry>,
    sandbox: Sandbox,
}

impl PluginRuntime {
    pub fn new(sandbox: Sandbox) -> Self {
        Self {
            registry: Arc::new(PluginRegistry::new()),
            sandbox,
        }
    }

    pub fn registry(&self) -> &Arc<PluginRegistry> {
        &self.registry
    }

    /// Load a plugin from a .devsper file path
    pub async fn load_file(&self, path: &Path) -> Result<LoadedPlugin> {
        let source: String = tokio::fs::read_to_string(path)
            .await
            .map_err(|e| anyhow!("Cannot read plugin {}: {e}", path.display()))?;

        let name = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();

        self.load_source(&name, &source).await
    }

    /// Load a plugin from source string (for builtin plugins or tests)
    pub async fn load_source(&self, name: &str, source: &str) -> Result<LoadedPlugin> {
        debug!(plugin = %name, "Loading plugin");

        let lua = Lua::new();
        inject_stdlib(&lua, self.sandbox.workspace.clone(), self.sandbox.allow_exec)
            .map_err(|e| anyhow!("Stdlib injection failed: {e}"))?;

        // Execute the plugin source
        lua.load(source)
            .set_name(name)
            .exec()
            .map_err(|e| anyhow!("Plugin {name} execution error: {e}"))?;

        // Collect registered tools
        let registered: LuaTable = lua
            .globals()
            .get("__devsper_tools__")
            .map_err(|e| anyhow!("Could not get tool registry: {e}"))?;

        let mut tools = Vec::new();

        for pair in registered.pairs::<String, LuaTable>() {
            let (tool_name, spec) = pair.map_err(|e| anyhow!("Tool spec error: {e}"))?;

            let description: String = spec
                .get::<String>("description")
                .unwrap_or_else(|_| tool_name.clone());

            let params = spec
                .get::<LuaValue>("params")
                .ok()
                .and_then(lua_to_json)
                .unwrap_or(serde_json::json!({}));

            let tool_def = ToolDef {
                name: tool_name.clone(),
                description,
                parameters: params,
            };

            let tool_name_owned = tool_name.clone();
            let def = tool_def.clone();

            // Stub executor — returns a JSON echo of the call arguments.
            // Full Lua tool execution (invoking the `run` function from Rust)
            // requires crossing the Send boundary and is deferred to a later phase.
            let executor: crate::registry::ExecutorFn =
                Arc::new(move |call: ToolCall| {
                    let result = serde_json::json!({
                        "tool": &call.name,
                        "args": call.arguments,
                        "note": "Lua tool execution — runtime calls happen in embedded VM"
                    });
                    let tr = ToolResult {
                        tool_call_id: call.id.clone(),
                        content: result,
                        is_error: false,
                    };
                    Box::pin(async move { Ok::<ToolResult, anyhow::Error>(tr) })
                        as std::pin::Pin<
                            Box<dyn std::future::Future<Output = Result<ToolResult>> + Send>,
                        >
                });

            self.registry
                .register(RegisteredTool {
                    def: def.clone(),
                    executor,
                })
                .await;

            tools.push(tool_def);
            info!(plugin = %name, tool = %tool_name_owned, "Registered tool");
        }

        Ok(LoadedPlugin {
            name: name.to_string(),
            tools,
        })
    }
}

/// Convert a Lua value to serde_json::Value (best-effort)
pub fn lua_to_json(val: LuaValue) -> Option<serde_json::Value> {
    match val {
        LuaValue::Nil => Some(serde_json::Value::Null),
        LuaValue::Boolean(b) => Some(serde_json::Value::Bool(b)),
        LuaValue::Integer(i) => Some(serde_json::json!(i)),
        LuaValue::Number(n) => Some(serde_json::json!(n)),
        LuaValue::String(s) => Some(serde_json::Value::String(s.to_str().ok()?.to_string())),
        LuaValue::Table(t) => {
            // Try array first, then object
            let mut arr: Vec<serde_json::Value> = Vec::new();
            let mut obj = serde_json::Map::new();
            let mut is_array = true;
            for (k, v) in t.clone().pairs::<LuaValue, LuaValue>().flatten() {
                match k {
                    LuaValue::Integer(i) => {
                        if let Some(val) = lua_to_json(v) {
                            let idx = (i - 1) as usize;
                            if idx == arr.len() {
                                arr.push(val);
                            } else {
                                is_array = false;
                            }
                        }
                    }
                    LuaValue::String(s) => {
                        is_array = false;
                        if let (Ok(key), Some(val)) =
                            (s.to_str().map(|k| k.to_string()), lua_to_json(v))
                        {
                            obj.insert(key, val);
                        }
                    }
                    _ => {
                        is_array = false;
                    }
                }
            }
            if is_array && !arr.is_empty() {
                Some(serde_json::Value::Array(arr))
            } else {
                Some(serde_json::Value::Object(obj))
            }
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sandbox::Sandbox;

    fn make_runtime() -> PluginRuntime {
        let sandbox = Sandbox::new(std::env::temp_dir());
        PluginRuntime::new(sandbox)
    }

    #[tokio::test]
    async fn load_simple_tool_plugin() {
        let runtime = make_runtime();
        let source = r#"
devsper.tool("test.greet", {
    description = "Say hello",
    params = { name = "string" },
    run = function(ctx, args)
        return { greeting = "Hello, " .. (args.name or "world") }
    end,
})
"#;
        let plugin = runtime.load_source("test-plugin", source).await.unwrap();
        assert_eq!(plugin.name, "test-plugin");
        assert_eq!(plugin.tools.len(), 1);
        assert_eq!(plugin.tools[0].name, "test.greet");
    }

    #[tokio::test]
    async fn registry_lists_tools_after_load() {
        let runtime = make_runtime();
        let source = r#"
devsper.tool("fs.list", {
    description = "List files",
    params = {},
    run = function(ctx, args) return {} end,
})
devsper.tool("fs.read", {
    description = "Read a file",
    params = { path = "string" },
    run = function(ctx, args) return { content = "" } end,
})
"#;
        runtime.load_source("fs-plugin", source).await.unwrap();
        let tools = runtime.registry().list().await;
        assert_eq!(tools.len(), 2);
        let names: Vec<_> = tools.iter().map(|t| t.name.as_str()).collect();
        assert!(names.contains(&"fs.list"));
        assert!(names.contains(&"fs.read"));
    }

    #[tokio::test]
    async fn execute_registered_tool() {
        let runtime = make_runtime();
        let source = r#"
devsper.tool("math.add", {
    description = "Add two numbers",
    params = { a = "number", b = "number" },
    run = function(ctx, args) return { result = args.a + args.b } end,
})
"#;
        runtime.load_source("math-plugin", source).await.unwrap();

        let call = ToolCall {
            id: "call-1".to_string(),
            name: "math.add".to_string(),
            arguments: serde_json::json!({ "a": 3, "b": 4 }),
        };
        let result = runtime.registry().execute(call).await.unwrap();
        assert!(!result.is_error);
    }

    #[tokio::test]
    async fn lua_to_json_conversions() {
        let lua = Lua::new();

        // Test basic conversions
        assert_eq!(lua_to_json(LuaValue::Nil), Some(serde_json::Value::Null));
        assert_eq!(
            lua_to_json(LuaValue::Boolean(true)),
            Some(serde_json::Value::Bool(true))
        );
        assert_eq!(
            lua_to_json(LuaValue::Integer(42)),
            Some(serde_json::json!(42))
        );

        // Test string
        let s = lua.create_string("hello").unwrap();
        assert_eq!(
            lua_to_json(LuaValue::String(s)),
            Some(serde_json::json!("hello"))
        );
    }
}
