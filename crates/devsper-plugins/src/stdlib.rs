use mlua::prelude::*;
use std::path::PathBuf;

/// Inject the `devsper` global table into a Lua VM
pub fn inject_stdlib(lua: &Lua, workspace: PathBuf, allow_exec: bool) -> LuaResult<()> {
    let devsper = lua.create_table()?;

    // devsper.log(level, msg)
    let log_fn = lua.create_function(|_, (level, msg): (String, String)| {
        match level.as_str() {
            "error" => tracing::error!(plugin = true, "{msg}"),
            "warn" => tracing::warn!(plugin = true, "{msg}"),
            "debug" => tracing::debug!(plugin = true, "{msg}"),
            _ => tracing::info!(plugin = true, "{msg}"),
        }
        Ok(())
    })?;
    devsper.set("log", log_fn)?;

    // devsper.exec(cmd, args) → {code, stdout, stderr}
    let ws = workspace.clone();
    let exec_fn = lua.create_function(move |lua_ctx, (cmd, args): (String, Vec<String>)| {
        if !allow_exec {
            return Err(LuaError::RuntimeError(
                "exec not allowed in this sandbox".to_string(),
            ));
        }

        let output = std::process::Command::new(&cmd)
            .args(&args)
            .current_dir(&ws)
            .output()
            .map_err(|e| LuaError::RuntimeError(format!("exec failed: {e}")))?;

        let result = lua_ctx.create_table()?;
        result.set("code", output.status.code().unwrap_or(-1))?;
        result.set(
            "stdout",
            String::from_utf8_lossy(&output.stdout).to_string(),
        )?;
        result.set(
            "stderr",
            String::from_utf8_lossy(&output.stderr).to_string(),
        )?;
        Ok(result)
    })?;
    devsper.set("exec", exec_fn)?;

    // devsper.ctx table
    let ctx = lua.create_table()?;
    ctx.set("workspace", workspace.to_string_lossy().to_string())?;
    devsper.set("ctx", ctx)?;

    // devsper.tool(name, spec) — stores registrations for later collection
    let registered = lua.create_table()?;
    lua.globals().set("__devsper_tools__", registered)?;

    let tool_fn = lua.create_function(|lua_ctx, (name, spec): (String, LuaTable)| {
        let registered: LuaTable = lua_ctx.globals().get("__devsper_tools__")?;
        registered.set(name, spec)?;
        Ok(())
    })?;
    devsper.set("tool", tool_fn)?;

    // devsper.workflow(config) — similar registration
    let wf_fn = lua.create_function(|lua_ctx, config: LuaTable| {
        lua_ctx
            .globals()
            .set("__devsper_workflow__", config.clone())?;
        Ok(config)
    })?;
    devsper.set("workflow", wf_fn)?;

    lua.globals().set("devsper", devsper)?;
    Ok(())
}
