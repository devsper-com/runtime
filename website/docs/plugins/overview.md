---
title: Plugin Overview
---

# Plugins Overview

Plugins extend devsper by adding new tools that agents can use at runtime. Each plugin is an external Python package that registers one or more tools via Python entry points. This keeps the core lean while allowing the ecosystem to grow independently.

## What Plugins Are

A plugin is a Python package that:

- Depends on `devsper` as a runtime dependency
- Declares a `devsper.plugins` entry point in its `pyproject.toml`
- Exports a callable that returns `Tool` instances or calls `register()` directly

Plugins provide **tools** -- stateless callable units with a name, description, JSON Schema for inputs, and a `run(**kwargs) -> str` method. Agents invoke these tools during task execution.

## How Plugins Work

devsper uses Python's `importlib.metadata` entry point mechanism to discover plugins at startup. The flow is:

1. **Discovery** -- The plugin loader scans all installed packages for the `devsper.plugins` entry point group.
2. **Loading** -- Each entry point's callable is imported and invoked.
3. **Registration** -- The callable either returns a list of `Tool` instances (which the loader registers) or calls `register()` directly.
4. **Availability** -- Registered tools appear in the global tool registry and become available to all agents.

```python
# Entry point in pyproject.toml
[project.entry-points."devsper.plugins"]
my_plugin = "my_plugin:load"
```

```python
# my_plugin/__init__.py
from devsper.tools.base import Tool
from devsper.tools.registry import register

class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def run(self, **kwargs) -> str:
        return "result"

def load():
    tool = MyTool()
    register(tool)
    return [tool]
```

## Plugin Lifecycle

The full lifecycle of a plugin from installation to use:

1. **Install** -- `pip install devsper-plugin-<name>` or `devsper reg install <package>`
2. **Load** -- On startup, the plugin loader discovers the entry point and calls the load function
3. **Register** -- Tools are added to the global registry via `register()`
4. **Select** -- When an agent runs a task, the tool selector picks relevant tools (optionally using smart top-k selection)
5. **Execute** -- The tool runner validates arguments against `input_schema` and calls `tool.run()`

## Built-in vs Plugin Tools

devsper ships with built-in tools organized by category: `research`, `coding`, `data_science`, `documents`, `experiments`, `memory`, `filesystem`, `system`, `knowledge`, and `flagship`. These are registered automatically when the `devsper.tools` package is imported.

Plugin tools work identically to built-in tools. They share the same `Tool` base class, the same registry, and the same execution pipeline. Agents cannot distinguish between built-in and plugin tools.

## The devsper Plugin Registry

The devsper plugin registry at [registry.devsper.com](https://registry.devsper.com) is a dedicated package index for devsper plugins. It provides:

- **Search and discovery** -- Find plugins by keyword or category
- **Verification** -- Uploaded plugins are validated server-side to ensure they load correctly
- **Version management** -- Track versions, download counts, and yank broken releases
- **CLI integration** -- Publish, search, and install directly from the `devsper reg` CLI

## Package Naming

Plugin packages follow the naming convention `devsper-plugin-<name>`. This makes them easy to find on PyPI and the devsper registry.

## Next Steps

- [Installing Plugins](/docs/plugins/installing) -- Install and manage plugins
- [Authoring Plugins](/docs/plugins/authoring) -- Create your own plugin
- [Hooks and API Reference](/docs/plugins/hooks-api) -- Tool and registry API details
- [Distribution](/docs/plugins/distribution) -- Publish and distribute your plugin
