---
title: "devsper tools"
---

# devsper tools

Tools are the capabilities available to agents during a swarm run. They include built-in operations (web search, file reading, code execution) and any tools added via [plugins](/docs/cli/plugins).

## How Tools Are Loaded

devsper discovers tools from two sources at startup:

1. **Built-in tools** — shipped with the `devsper` package.
2. **Plugin tools** — installed via `devsper reg install` and registered through Python entry points.

All discovered tools are loaded unless restricted by the `[tools] enabled` list in your config. Use `devsper doctor` to see what is loaded.

## Checking Tool Status

### devsper doctor

The `devsper doctor` command reports tool loading status:

```bash
devsper doctor
```

Example output:

```
Config:    devsper.toml (valid)
Models:    gpt-4o (accessible)
Memory:    sqlite (.devsper/memory.db)
Tools:     12 loaded (2 from plugins)
Plugins:   devsper-web-scraper (v1.2.0), devsper-pdf-reader (v0.9.1)
```

If a tool fails to load, doctor displays the error and suggests a fix.

### devsper analytics

View usage statistics for tools across past runs:

```bash
devsper analytics
```

This shows which tools were invoked, how often, and their average execution time. Useful for identifying underused tools or performance bottlenecks.

## Tool Selection Config

Configure tool availability and selection in `devsper.toml`:

```toml
[tools]
enabled = ["web_search", "file_reader", "code_exec"]
top_k = 5
```

- **`enabled`** — restrict loaded tools to this list. Omit the field to load all available tools (built-in and plugin).
- **`top_k`** — maximum number of tools selected per individual task.

### Smart Tool Selection

Not every tool is relevant to every task. devsper uses smart tool selection to choose the most appropriate tools for each subtask during a run. The planner evaluates the task description against tool capabilities and selects up to `top_k` tools.

This reduces prompt size and improves agent focus. You can tune `top_k` in your config:

```toml
[tools]
top_k = 3    # fewer tools, more focused agents
top_k = 10   # more tools, broader capability per task
```

Lower values work well for specific, well-defined tasks. Higher values suit exploratory or multi-step work.

## Tool Categories

Built-in tools are organized into categories:

| Category | Examples |
|----------|----------|
| Search | `web_search`, `knowledge_query` |
| File I/O | `file_reader`, `file_writer` |
| Code | `code_exec`, `code_analysis` |
| Data | `json_parser`, `csv_reader` |
| System | `shell_exec`, `http_request` |

Plugin tools may add additional categories. Use `devsper doctor` to see the full list of available tools in your environment.

## Using Tools in Runs

Tools are selected and invoked automatically during `devsper run`:

```bash
devsper run "find recent papers on transformer architectures"
```

The planner decomposes the task, selects appropriate tools for each subtask, and agents invoke them as needed. No manual tool invocation is required.

To see which tools were used in a completed run:

```bash
devsper analyze <run_id>
devsper analytics
```

## Debugging Tool Issues

### Tool not loading

1. Run `devsper doctor` to check for load errors.
2. Verify the tool is listed in `[tools] enabled` (if the field is set).
3. For plugin tools, verify the plugin is installed: `pip list | grep devsper-`.

### Tool not being selected

If a tool is loaded but never used during runs:

1. Check that `top_k` is high enough to include it.
2. Review the task description — smart selection may not consider the tool relevant.
3. Use `devsper analytics` to see historical tool selection patterns.

### Tool execution errors

1. Run with `--debug` for detailed tool execution logs:

```bash
devsper --debug run "your task"
```

2. Check that any external dependencies the tool requires are available (API keys, network access, system binaries).
3. Verify credentials with `devsper credentials list`.

## Related

- [Plugin management](/docs/cli/plugins) — installing and configuring plugin tools
- [Configuration reference](/docs/cli/config) — `[tools]` config section
- [CLI overview](/docs/cli/overview) — all devsper commands
