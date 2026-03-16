---
title: Hooks API
---

# Tool and Plugin API Reference

This page documents the core APIs for tools, the tool registry, the plugin loader, and the smart tool selector.

## Tool Base Class

**Module:** `devsper.tools.base`

```python
from devsper.tools.base import Tool
```

`Tool` is an abstract base class. All tools -- built-in and plugin -- inherit from it.

### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | `""` | Unique identifier for the tool |
| `description` | `str` | `""` | Human-readable description (used by smart selector) |
| `input_schema` | `dict` | `{}` | JSON Schema defining accepted keyword arguments |
| `category` | `str` | `""` | Optional category label for filtering |

### Methods

#### `run(**kwargs) -> str`

Abstract method. Execute the tool with the given arguments and return a string result. Arguments correspond to properties defined in `input_schema`.

```python
class MyTool(Tool):
    name = "my_tool"
    description = "Example tool"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }

    def run(self, **kwargs) -> str:
        query = kwargs["query"]
        return f"Results for: {query}"
```

## Tool Registry

**Module:** `devsper.tools.registry`

The registry is the global store of all available tools.

### `register(tool: Tool) -> None`

Register a tool by its `name`. If a tool with the same name already exists, it is overwritten.

```python
from devsper.tools.registry import register

register(MyTool())
```

### `get(name: str) -> Tool | None`

Return the tool with the given name, or `None` if not found.

```python
from devsper.tools.registry import get

tool = get("my_tool")
```

### `list_tools() -> list[Tool]`

Return all registered tools.

```python
from devsper.tools.registry import list_tools

for tool in list_tools():
    print(f"{tool.name}: {tool.description}")
```

### `get_with_mcp_fallback(name: str) -> Tool | None`

Look up a tool by name. If not found and the name has no dot, search for a single MCP-style tool whose name ends with `.<name>`. This lets agents use short names when only one matching MCP tool is registered.

## Tool Runner

**Module:** `devsper.tools.tool_runner`

### `run_tool(name: str, args: dict, task_type: str | None = None) -> str`

Execute a tool by name with validated arguments. This is the primary execution entry point used by agents.

**Behavior:**

1. Looks up the tool via `get_with_mcp_fallback(name)`
2. Validates `args` against the tool's `input_schema` (checks required fields and types)
3. Calls `tool.run(**args)`
4. Returns the string result
5. Records analytics and scoring data

**Error responses:**

| Condition | Return value |
|-----------|-------------|
| Tool not found | `"Tool not found: <name>"` |
| Validation failure | `"Validation error: <details>"` |
| Runtime exception | `"Tool error: <ExceptionType>: <message>"` |

```python
from devsper.tools.tool_runner import run_tool

result = run_tool("word_count", {"text": "hello world"})
# Returns: "2 words"
```

### Argument Validation

The runner validates arguments against `input_schema` before execution:

- Required fields must be present
- Type checking for `string`, `number`, `integer`, `boolean`, `array`, and `object`
- Unknown fields are allowed (no strict additional-properties check)

## Plugin Loader

**Module:** `devsper.plugins.plugin_loader`

### `load_plugins(enabled: list[str] | None = None) -> list[str]`

Discover and load all plugins from the `devsper.plugins` entry point group.

**Parameters:**

- `enabled` -- If provided, only load plugins whose entry point name is in this list. If `None`, load all discovered plugins.

**Returns:** List of plugin names that were loaded.

**Behavior:**

1. Scans `importlib.metadata.entry_points(group="devsper.plugins")`
2. For each entry point, calls the referenced callable
3. If the callable returns a list of `Tool` instances, registers each one
4. If the callable returns `None`, assumes it called `register()` internally
5. Records plugin metadata (name, version, tool names) in the plugin registry

```python
from devsper.plugins.plugin_loader import load_plugins

loaded = load_plugins()
# Returns: ["demo", "web", ...]
```

## Plugin Registry

**Module:** `devsper.plugins.plugin_registry`

Tracks metadata about loaded plugins. This is an internal registry (distinct from the web registry).

### `PluginInfo`

Dataclass with fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Plugin entry point name |
| `version` | `str` | Version from the package distribution |
| `tools_registered` | `list[str]` | Names of tools registered by this plugin |

### `register_plugin(name, version, tools) -> None`

Record a loaded plugin.

### `get_plugin(name: str) -> PluginInfo | None`

Look up a plugin by name.

### `list_plugins() -> list[PluginInfo]`

Return all loaded plugins.

### `clear_plugins() -> None`

Clear the plugin registry (primarily for tests).

## Smart Tool Selector

**Module:** `devsper.tools.selector`

The selector filters and ranks tools for a given task using category filtering and semantic similarity.

### `select_tools_for_task(task_description, top_k=12, enabled_categories=None) -> list[Tool]`

Return the most relevant tools for a task.

**Parameters:**

- `task_description` -- Natural language description of the task
- `top_k` -- Maximum number of tools to return. If `<= 0`, returns all tools.
- `enabled_categories` -- If set, only consider tools in these categories

**How it works:**

1. Retrieves all registered tools
2. Filters by `enabled_categories` if specified
3. Embeds the task description and each tool's `"name: description"` text
4. Ranks tools by cosine similarity between embeddings
5. Returns the top-k results

### `get_tools_for_task(task_description, config=None, role=None, score_store=None) -> list[Tool]`

Higher-level function used by agents. Reads `top_k` and `enabled` categories from the devsper config (under `[tools]`), and optionally uses score-based ranking when a `score_store` is provided.

### Configuration

Enable smart selection in your devsper config:

```toml
[tools]
top_k = 12
enabled = ["research", "coding", "filesystem"]
```

When `top_k` is `0` or unset, all tools are passed to the agent without filtering.
