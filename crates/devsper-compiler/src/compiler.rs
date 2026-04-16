use crate::ir::WorkflowIr;
use anyhow::{anyhow, Result};
use mlua::prelude::*;
use std::path::{Path, PathBuf};
use tracing::info;

/// Options for compilation
#[derive(Debug, Clone, Default)]
pub struct CompileOptions {
    /// Embed runtime into standalone binary (--embed flag)
    pub embed: bool,
    /// Output path override (default: input + .bin)
    pub output: Option<PathBuf>,
}

/// Compiles .devsper source files
pub struct Compiler {
    options: CompileOptions,
}

impl Compiler {
    pub fn new(options: CompileOptions) -> Self {
        Self { options }
    }

    /// Parse and validate a .devsper source file, returning the IR
    pub fn parse_file(&self, path: &Path) -> Result<WorkflowIr> {
        let source = std::fs::read_to_string(path)
            .map_err(|e| anyhow!("Cannot read {}: {e}", path.display()))?;
        self.parse_source(&source)
    }

    /// Parse and validate .devsper source from a string, returning the IR
    pub fn parse_source(&self, source: &str) -> Result<WorkflowIr> {
        let lua = Lua::new();
        self.inject_compiler_stdlib(&lua)?;

        lua.load(source)
            .set_name("devsper")
            .exec()
            .map_err(|e| anyhow!("Parse error: {e}"))?;

        self.extract_ir(&lua)
    }

    /// Compile .devsper source to bytecode file (.devsper.bin)
    pub fn compile_to_bytecode(&self, source_path: &Path) -> Result<PathBuf> {
        let source = std::fs::read_to_string(source_path)
            .map_err(|e| anyhow!("Cannot read {}: {e}", source_path.display()))?;

        let lua = Lua::new();
        self.inject_compiler_stdlib(&lua)?;

        // Validate first
        lua.load(&source)
            .set_name(source_path.to_string_lossy().as_ref())
            .exec()
            .map_err(|e| anyhow!("Compile error: {e}"))?;

        let ir = self.extract_ir(&lua)?;

        // Serialize IR to JSON as the "bytecode" format
        // (mlua chunk dump requires unsafe; JSON IR is portable and inspectable)
        let output_path = self.options.output.clone().unwrap_or_else(|| {
            let mut p = source_path.to_path_buf();
            let name = p
                .file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("workflow")
                .to_string();
            p.set_file_name(format!("{name}.bin"));
            p
        });

        let bytes = serde_json::to_vec_pretty(&ir)
            .map_err(|e| anyhow!("IR serialization error: {e}"))?;

        std::fs::write(&output_path, bytes)
            .map_err(|e| anyhow!("Cannot write {}: {e}", output_path.display()))?;

        info!("Compiled to {}", output_path.display());
        Ok(output_path)
    }

    /// Inject the compiler-side devsper stdlib (collects IR, doesn't execute)
    fn inject_compiler_stdlib(&self, lua: &Lua) -> Result<()> {
        let devsper = lua.create_table().map_err(|e| anyhow!("create_table: {e}"))?;

        // State tables
        let tasks: LuaTable = lua.create_table().map_err(|e| anyhow!("create_table tasks: {e}"))?;
        let plugins: LuaTable = lua.create_table().map_err(|e| anyhow!("create_table plugins: {e}"))?;
        let inputs: LuaTable = lua.create_table().map_err(|e| anyhow!("create_table inputs: {e}"))?;
        lua.globals().set("__tasks__", tasks).map_err(|e| anyhow!("set __tasks__: {e}"))?;
        lua.globals().set("__plugins__", plugins).map_err(|e| anyhow!("set __plugins__: {e}"))?;
        lua.globals().set("__inputs__", inputs).map_err(|e| anyhow!("set __inputs__: {e}"))?;
        lua.globals()
            .set("__workflow__", lua.create_table().map_err(|e| anyhow!("create_table wf: {e}"))?)
            .map_err(|e| anyhow!("set __workflow__: {e}"))?;

        // devsper.workflow(config) → returns a workflow builder object
        let wf_fn = lua
            .create_function(|lua_ctx, config: LuaTable| {
                lua_ctx.globals().set("__workflow__", config.clone())?;

                let builder = lua_ctx.create_table()?;

                // wf.task(id, spec)
                let task_fn =
                    lua_ctx.create_function(|ctx, (id, spec): (String, LuaTable)| {
                        let tasks: LuaTable = ctx.globals().get("__tasks__")?;
                        spec.set("id", id.clone())?;
                        tasks.set(id, spec)?;
                        Ok(())
                    })?;
                builder.set("task", task_fn)?;

                // wf.plugin(name, spec)
                let plugin_fn =
                    lua_ctx.create_function(|ctx, (name, spec): (String, LuaTable)| {
                        let plugins: LuaTable = ctx.globals().get("__plugins__")?;
                        plugins.set(name, spec)?;
                        Ok(())
                    })?;
                builder.set("plugin", plugin_fn)?;

                // wf.input(name, spec)
                let input_fn =
                    lua_ctx.create_function(|ctx, (name, spec): (String, LuaTable)| {
                        let inputs: LuaTable = ctx.globals().get("__inputs__")?;
                        inputs.set(name, spec)?;
                        Ok(())
                    })?;
                builder.set("input", input_fn)?;

                Ok(builder)
            })
            .map_err(|e| anyhow!("create workflow fn: {e}"))?;
        devsper
            .set("workflow", wf_fn)
            .map_err(|e| anyhow!("set workflow: {e}"))?;

        // devsper.tool(name, spec) — for tool-only .devsper files
        let tool_fn = lua
            .create_function(|_, (_name, _spec): (String, LuaTable)| {
                Ok(()) // tools are handled by the plugin runtime, not the compiler IR
            })
            .map_err(|e| anyhow!("create tool fn: {e}"))?;
        devsper
            .set("tool", tool_fn)
            .map_err(|e| anyhow!("set tool: {e}"))?;

        // No-op stubs so plugin sources don't error during compilation analysis
        let noop = lua
            .create_function(|_, _: LuaValue| Ok(()))
            .map_err(|e| anyhow!("create noop fn: {e}"))?;
        devsper
            .set("log", noop)
            .map_err(|e| anyhow!("set log: {e}"))?;

        let exec_fn = lua
            .create_function(|lua_ctx, _: LuaValue| {
                let t = lua_ctx.create_table()?;
                t.set("code", 0)?;
                t.set("stdout", "")?;
                t.set("stderr", "")?;
                Ok(t)
            })
            .map_err(|e| anyhow!("create exec fn: {e}"))?;
        devsper
            .set("exec", exec_fn)
            .map_err(|e| anyhow!("set exec: {e}"))?;

        let ctx_table = lua.create_table().map_err(|e| anyhow!("create ctx table: {e}"))?;
        ctx_table
            .set("workspace", ".")
            .map_err(|e| anyhow!("set workspace: {e}"))?;
        ctx_table
            .set("run_id", "")
            .map_err(|e| anyhow!("set run_id: {e}"))?;
        devsper
            .set("ctx", ctx_table)
            .map_err(|e| anyhow!("set ctx: {e}"))?;

        lua.globals()
            .set("devsper", devsper)
            .map_err(|e| anyhow!("set devsper global: {e}"))?;
        Ok(())
    }

    /// Extract WorkflowIr from the Lua globals after execution
    fn extract_ir(&self, lua: &Lua) -> Result<WorkflowIr> {
        let mut ir = WorkflowIr::default();

        // Extract workflow config
        let wf: LuaTable = lua
            .globals()
            .get("__workflow__")
            .map_err(|e| anyhow!("No workflow config found: {e}"))?;

        if let Ok(name) = wf.get::<String>("name") {
            ir.name = name;
        }
        if let Ok(model) = wf.get::<String>("model") {
            ir.model = model;
        }
        if let Ok(workers) = wf.get::<u64>("workers") {
            ir.workers = workers as usize;
        }
        if let Ok(bus) = wf.get::<String>("bus") {
            ir.bus = bus;
        }

        // Evolution config
        if let Ok(evo) = wf.get::<LuaTable>("evolution") {
            if let Ok(v) = evo.get::<bool>("allow_mutations") {
                ir.evolution.allow_mutations = v;
            }
            if let Ok(v) = evo.get::<u32>("max_depth") {
                ir.evolution.max_depth = v;
            }
            if let Ok(v) = evo.get::<bool>("speculative") {
                ir.evolution.speculative = v;
            }
        }

        // Tasks
        let tasks: LuaTable = lua
            .globals()
            .get("__tasks__")
            .map_err(|e| anyhow!("No tasks table: {e}"))?;

        for pair in tasks.pairs::<String, LuaTable>() {
            let (id, spec) = pair.map_err(|e| anyhow!("Task parse error: {e}"))?;
            let prompt: String = spec.get("prompt").unwrap_or_default();
            let model: Option<String> = spec.get("model").ok();
            let can_mutate: bool = spec.get("can_mutate").unwrap_or(false);
            let depends_on: Vec<String> = spec
                .get::<LuaTable>("depends_on")
                .ok()
                .map(|t| {
                    t.sequence_values::<String>()
                        .filter_map(|r| r.ok())
                        .collect()
                })
                .unwrap_or_default();

            ir.tasks.push(crate::ir::TaskIr {
                id,
                prompt,
                model,
                can_mutate,
                depends_on,
            });
        }

        // Plugins
        let plugins: LuaTable = lua
            .globals()
            .get("__plugins__")
            .map_err(|e| anyhow!("No plugins table: {e}"))?;

        for pair in plugins.pairs::<String, LuaTable>() {
            let (name, spec) = pair.map_err(|e| anyhow!("Plugin parse error: {e}"))?;
            let source: String = spec
                .get("source")
                .unwrap_or_else(|_| format!("builtin:{name}"));
            ir.plugins.push(crate::ir::PluginRef { name, source });
        }

        // Inputs
        let inputs: LuaTable = lua
            .globals()
            .get("__inputs__")
            .map_err(|e| anyhow!("No inputs table: {e}"))?;

        for pair in inputs.pairs::<String, LuaTable>() {
            let (name, spec) = pair.map_err(|e| anyhow!("Input parse error: {e}"))?;
            let input_type: String = spec
                .get("type")
                .unwrap_or_else(|_| "string".to_string());
            let required: bool = spec.get("required").unwrap_or(false);
            let default: Option<String> = spec.get("default").ok();
            ir.inputs.insert(
                name,
                crate::ir::InputIr {
                    input_type,
                    required,
                    default,
                },
            );
        }

        Ok(ir)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_WORKFLOW: &str = r#"
local devsper = devsper

local wf = devsper.workflow({
    name = "test-workflow",
    model = "claude-sonnet-4-6",
    workers = 2,
    bus = "memory",
    evolution = {
        allow_mutations = true,
        max_depth = 5,
        speculative = false,
    },
})

wf.task("plan", {
    prompt = "Decompose the task",
    model = "claude-opus-4-6",
    can_mutate = true,
    depends_on = {},
})

wf.task("execute", {
    prompt = "Execute the plan",
    depends_on = {"plan"},
})

wf.plugin("git", { source = "builtin:git" })
wf.plugin("fs",  { source = "builtin:filesystem" })

wf.input("repo_url", { type = "string", required = true })
wf.input("branch",   { type = "string", default = "main" })

return wf
"#;

    #[test]
    fn parse_sample_workflow() {
        let compiler = Compiler::new(CompileOptions::default());
        let ir = compiler.parse_source(SAMPLE_WORKFLOW).unwrap();

        assert_eq!(ir.name, "test-workflow");
        assert_eq!(ir.model, "claude-sonnet-4-6");
        assert_eq!(ir.workers, 2);
        assert_eq!(ir.evolution.max_depth, 5);
        assert_eq!(ir.tasks.len(), 2);
        assert_eq!(ir.plugins.len(), 2);
        assert_eq!(ir.inputs.len(), 2);
    }

    #[test]
    fn task_dependencies_extracted() {
        let compiler = Compiler::new(CompileOptions::default());
        let ir = compiler.parse_source(SAMPLE_WORKFLOW).unwrap();

        let execute = ir.tasks.iter().find(|t| t.id == "execute").unwrap();
        assert_eq!(execute.depends_on, vec!["plan"]);
    }

    #[test]
    fn can_mutate_flag_extracted() {
        let compiler = Compiler::new(CompileOptions::default());
        let ir = compiler.parse_source(SAMPLE_WORKFLOW).unwrap();

        let plan = ir.tasks.iter().find(|t| t.id == "plan").unwrap();
        assert!(plan.can_mutate);
        let execute = ir.tasks.iter().find(|t| t.id == "execute").unwrap();
        assert!(!execute.can_mutate);
    }

    #[test]
    fn plugins_extracted() {
        let compiler = Compiler::new(CompileOptions::default());
        let ir = compiler.parse_source(SAMPLE_WORKFLOW).unwrap();

        let git = ir.plugins.iter().find(|p| p.name == "git").unwrap();
        assert_eq!(git.source, "builtin:git");
    }

    #[test]
    fn inputs_extracted() {
        let compiler = Compiler::new(CompileOptions::default());
        let ir = compiler.parse_source(SAMPLE_WORKFLOW).unwrap();

        let repo_url = ir.inputs.get("repo_url").unwrap();
        assert!(repo_url.required);
        assert_eq!(repo_url.input_type, "string");

        let branch = ir.inputs.get("branch").unwrap();
        assert!(!branch.required);
        assert_eq!(branch.default.as_deref(), Some("main"));
    }

    #[test]
    fn invalid_lua_returns_error() {
        let compiler = Compiler::new(CompileOptions::default());
        let result = compiler.parse_source("this is not valid lua }{{{");
        assert!(result.is_err());
    }

    #[test]
    fn compile_to_bytecode_writes_file() {
        let compiler = Compiler::new(CompileOptions::default());
        let dir = tempfile::tempdir().unwrap();
        let source_path = dir.path().join("test.devsper");
        std::fs::write(&source_path, SAMPLE_WORKFLOW).unwrap();

        let output = compiler.compile_to_bytecode(&source_path).unwrap();
        assert!(output.exists());

        // Output is valid JSON IR
        let content = std::fs::read_to_string(&output).unwrap();
        let ir: WorkflowIr = serde_json::from_str(&content).unwrap();
        assert_eq!(ir.name, "test-workflow");
    }
}
