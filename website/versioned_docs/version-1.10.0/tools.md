# Tool System

## Tool Architecture

Tools are **stateless** callable units that agents use to perform actions (read files, run code, search memory, call external APIs, etc.). Each tool has:

- A **name** (unique in the registry)
- A **description** (for the agent prompt)
- An **input_schema** (JSON Schema–style: `type`, `properties`, `required`)
- A **run(**kwargs)** method that returns a **string** (so the agent can parse or display the result)

The agent receives a list of tools and invokes them by outputting a fixed format (e.g. `TOOL: <name>` and `INPUT: <json>`). The **tool runner** validates arguments, calls the tool, and returns the result string (or an error message).

## Tool Registry

- **Registration:** Tools register themselves when their module is imported (e.g. in each category’s `__init__.py` via `register(SomeTool())`).
- **Lookup:** `get(name)` returns the `Tool` for that name; `list_tools()` returns all registered tools.
- **Usage:** The agent (or any code) uses `run_tool(name, args)` to execute a tool by name with a dict of arguments.

## Tool Runner

- **Role:** Execute a tool by name with validated arguments and safe error handling.
- **Steps:**  
  1. Resolve tool by name from the registry.  
  2. Validate `args` against the tool’s `input_schema` (required keys, types).  
  3. Call `tool.run(**args)`.  
  4. Return the result string, or a formatted error string on validation failure or exception.

## Creating a New Tool

1. Subclass `Tool` from `devsper.tools.base`.
2. Set `name`, `description`, and `input_schema` (e.g. `properties`, `required`).
3. Implement `run(self, **kwargs) -> str`.
4. Register the tool so it’s loaded (e.g. in the package’s `__init__.py` or a category `__init__.py`): `register(MyTool())`.

**Example implementation:**

```python
from pathlib import Path
from devsper.tools.base import Tool
from devsper.tools.registry import register


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file. Creates parent dirs if needed. Overwrites existing file."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }

    def run(self, **kwargs) -> str:
        path = kwargs.get("path")
        content = kwargs.get("content")
        if not path or not isinstance(path, str):
            return "Error: path must be a non-empty string"
        if content is None:
            return "Error: content is required"
        p = Path(path).resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} characters to {p}"
        except Exception as e:
            return f"Error writing file: {e}"


register(WriteFileTool())
```

Ensure the module is imported (e.g. in `devsper.tools` or the right category `__init__.py`) so the tool is registered when the app loads.

## Tool Categories

Tools are grouped by domain; each category lives in its own subpackage and registers in its `__init__.py`. Categories include:

| Category | Examples |
|----------|----------|
| **Research** | literature review, citation graph, topic extraction, arxiv search, web search |
| **Coding** | codebase indexer, dependency graph, architecture analyzer, refactor candidates, run Python, lint, generate tests |
| **Data science** | dataset profile, outlier detection, correlation, distribution report, feature importance |
| **Documents** | docproc extraction, knowledge graph, timeline extraction, summarize, convert to Markdown |
| **Experiments** | grid search, swarm experiment runner, Monte Carlo, statistical tests, result comparator |
| **Memory** | store, list, search, summarize, tag, delete memory |
| **Filesystem** | read_file, write_file, list_directory, search_files, file metadata |
| **System** | run_shell_command, environment variables, disk/cpu/memory usage |
| **Knowledge** | document topic extractor, citation graph builder, knowledge graph extractor, timeline extractor |
| **Flagship** | docproc corpus pipeline, research graph builder, repository semantic map, distributed document analysis |

Use `list_tools()` or inspect the `devsper.tools` package to see the full set (120+ tools).

## Smart tool selection (v1)

When config has `[tools] top_k > 0`, the agent does **not** receive all tools. Instead:

- **Tool selector** (`devsper.tools.selector`): embeds the task description and each tool’s name + description (using the same embedding function as memory), computes cosine similarity, and returns the **top_k** most relevant tools.
- **Category filter:** If `[tools] enabled` is set (e.g. `["research", "coding", "documents"]`), only tools in those categories are considered; then top_k is applied within that set.
- **Tool category:** Each tool can set an optional `category` attribute (e.g. `"research"`, `"coding"`). If unset, the selector infers it from the tool’s module path (e.g. `devsper.tools.research.*` → `research`).

This keeps the agent prompt smaller and focuses it on the most relevant tools for the task.

## Plugin system (v1)

External packages can register tools without modifying the devsper codebase.

- **Entry point:** Declare a group `devsper.plugins` in your package’s `pyproject.toml`:
  ```toml
  [project.entry-points."devsper.plugins"]
  bio = "devsper_plugin_bio:register"
  ```
- **Loader:** When `devsper.tools` is imported, the **plugin loader** (`devsper.plugins.plugin_loader`) discovers all entry points, loads each callable, and expects either a list of `Tool` instances or a function that registers tools with `devsper.tools.registry.register`.
- **Registry:** Loaded plugins are recorded in `devsper.plugins.plugin_registry` (name, version, list of tool names registered).

Example plugin implementation: the callable can return `[Tool1(), Tool2()]` or call `register(tool)` for each tool and return nothing. See [Development](development) for project structure and adding plugins.
