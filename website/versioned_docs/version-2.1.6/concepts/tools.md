---
title: Tools
---

# Tool System

## Tool Architecture

Tools are **stateless** callable units that agents use to perform actions (read files, run code, search memory, call external APIs, etc.). Each tool has:

- A **name** (unique in the registry)
- A **description** (for the agent prompt)
- An **input_schema** (JSON Schema-style: `type`, `properties`, `required`)
- A **run(**kwargs)** method that returns a **string**

The agent receives a list of tools and invokes them by outputting a fixed format. The **tool runner** validates arguments, calls the tool, and returns the result string (or an error message).

## Creating a New Tool

1. Subclass `Tool` from `devsper.tools.base`.
2. Set `name`, `description`, and `input_schema`.
3. Implement `run(self, **kwargs) -> str`.
4. Register the tool in the package's `__init__.py`: `register(MyTool())`.

```python
from pathlib import Path
from devsper.tools.base import Tool
from devsper.tools.registry import register

class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file."
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
        p = Path(path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {p}"

register(WriteFileTool())
```

## Tool Categories

| Category | Examples |
|----------|----------|
| **Research** | literature review, citation graph, arxiv search, web search |
| **Coding** | codebase indexer, dependency graph, run Python, lint |
| **Data science** | dataset profile, outlier detection, correlation |
| **Documents** | docproc extraction, knowledge graph, summarize |
| **Memory** | store, list, search, summarize, tag, delete memory |
| **Filesystem** | read_file, write_file, list_directory, search_files |
| **System** | run_shell_command, environment variables |

Use `list_tools()` or inspect the `devsper.tools` package to see the full set (120+ tools).
