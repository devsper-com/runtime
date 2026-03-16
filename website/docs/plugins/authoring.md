---
title: Authoring Plugins
---

# Authoring Plugins

This guide walks through creating a devsper plugin from scratch. A plugin is a Python package that registers one or more tools via the `devsper.plugins` entry point.

## Project Structure

A minimal plugin package looks like this:

```
devsper-plugin-example/
  devsper_plugin_example/
    __init__.py
  pyproject.toml
  README.md
```

The Python package name uses underscores (`devsper_plugin_example`) while the distribution name uses hyphens (`devsper-plugin-example`).

## pyproject.toml

The entry point declaration is what tells devsper about your plugin:

```toml
[project]
name = "devsper-plugin-example"
version = "0.1.0"
description = "An example devsper plugin"
license = "MIT"
requires-python = ">=3.12"
dependencies = [
    "devsper",
]

[project.entry-points."devsper.plugins"]
example = "devsper_plugin_example:load"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["devsper_plugin_example"]
```

The key section is `[project.entry-points."devsper.plugins"]`. The left side (`example`) is the plugin name used by the loader. The right side points to a callable -- typically a `load` function in your package.

## Implementing a Tool

Tools subclass `Tool` from `devsper.tools.base` and define four attributes plus a `run` method:

```python
from devsper.tools.base import Tool

class WordCountTool(Tool):
    name = "word_count"
    description = "Count the number of words in a text string"
    input_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to count words in",
            },
        },
        "required": ["text"],
    }
    category = "documents"

    def run(self, **kwargs) -> str:
        text = kwargs.get("text", "")
        count = len(text.split())
        return f"{count} words"
```

### Tool Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique identifier for the tool |
| `description` | `str` | Short explanation of what the tool does (used by tool selector) |
| `input_schema` | `dict` | JSON Schema defining accepted arguments |
| `category` | `str` | Optional category label for filtering |

### The `run` Method

- Accepts `**kwargs` matching the properties in `input_schema`
- Must return a `str` -- agents parse the string output
- Tools are stateless: do not store state between invocations
- On failure, return a descriptive error string (e.g., `"Tool error: file not found"`)

### Categories

Valid categories include: `research`, `coding`, `data_science`, `documents`, `experiments`, `memory`, `filesystem`, `system`, `knowledge`, and `flagship`. If `category` is unset, the selector infers it from the tool's module path.

## Registration

Your entry point callable must either return a list of `Tool` instances or call `register()` directly:

```python
from devsper.tools.base import Tool
from devsper.tools.registry import register

class WordCountTool(Tool):
    # ... (as above)
    pass

def load():
    """Plugin entry point."""
    tool = WordCountTool()
    register(tool)
    return [tool]
```

Both patterns work:

- **Return a list** -- The loader registers each `Tool` in the returned list.
- **Call `register()` and return `None`** -- The loader detects that registration was handled internally.

## Testing Locally

Install your plugin in editable mode and verify it loads:

```bash
pip install -e .
devsper doctor
```

You can also validate your plugin structure with the built-in test command:

```bash
devsper reg test
```

This checks that your `pyproject.toml` has the required fields, that the entry point loads without errors, and that it returns valid `Tool` objects.

To test the tool itself:

```python
from devsper_plugin_example import load

tools = load()
result = tools[0].run(text="hello world")
assert result == "2 words"
```

## Complete Example

Here is a full plugin that provides an echo tool:

```python
# devsper_plugin_echo/__init__.py
from devsper.tools.base import Tool
from devsper.tools.registry import register

class EchoTool(Tool):
    name = "echo"
    description = "Echo back the provided message"
    input_schema = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo"},
        },
        "required": ["message"],
    }
    category = "system"

    def run(self, **kwargs) -> str:
        return kwargs.get("message", "")

def load():
    tool = EchoTool()
    register(tool)
    return [tool]
```

## Best Practices

- **Naming** -- Use descriptive, unique tool names. Avoid collisions with built-in tools.
- **Schemas** -- Define `input_schema` thoroughly. Include `description` for each property so agents understand the expected input.
- **Error handling** -- Return error strings rather than raising exceptions. The tool runner catches exceptions, but explicit error messages are more informative.
- **Dependencies** -- Keep plugin dependencies minimal. Heavy imports should be deferred to the `run` method if possible.
- **Statelessness** -- Do not rely on instance state between calls. Each `run()` invocation should be self-contained.

## Next Steps

- [Hooks and API Reference](/docs/plugins/hooks-api) -- Full API documentation
- [Distribution](/docs/plugins/distribution) -- Publish your plugin
- [Plugin Overview](/docs/plugins/overview) -- Architecture and lifecycle
