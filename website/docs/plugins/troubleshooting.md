---
title: Troubleshooting
---

# Troubleshooting

This page covers common issues encountered when developing and using hivemind plugins, along with their solutions.

## Plugin Not Loading

### Entry Point Misconfigured

The most common cause of a plugin failing to load is an incorrect entry point in `pyproject.toml`. The entry point must be under the `hivemind.plugins` group:

```toml
[project.entry-points."hivemind.plugins"]
my_plugin = "my_plugin.module:register_tools"
```

Verify the dotted module path matches your actual package structure. The function referenced (e.g., `register_tools`) must be importable from the specified module.

### Import Errors

If your plugin module raises an `ImportError` at import time, hivemind silently skips it by default. To surface these errors, enable debug mode:

```bash
HIVEMIND_DEBUG=1 hivemind doctor
```

This will print the full traceback for any plugin that fails to import. Common causes include missing dependencies or syntax errors in your plugin code.

### Plugin Installed in Wrong Environment

Ensure the plugin is installed in the same Python environment as hivemind:

```bash
which python
pip show hivemind-ai
pip show my-plugin
```

All three should point to the same environment.

## Tools Not Appearing

### Registration Not Called

Your entry point function must explicitly call `register()` for each tool:

```python
from hivemind.tools.registry import register

def register_tools():
    register(MyTool())
```

If `register()` is never called, the tools will not be available to the runtime even though the plugin loads successfully.

### Tool Category Not Enabled

Check your hivemind configuration. If you use the `[tools]` section to restrict enabled categories, your plugin's tools must belong to an enabled category:

```toml
[tools]
enabled = ["research", "coding", "my_custom_category"]
```

### Verifying Registered Tools

Use `hivemind doctor` to list all registered tools and confirm your tools appear:

```bash
hivemind doctor
```

You can also call `list_tools()` programmatically to inspect the registry at runtime.

## Schema Validation Errors

Tool input schemas must be valid JSON Schema. Common mistakes:

- Missing `type` field on a property.
- Using `required` at the property level instead of the object level.
- Mismatched property names between `properties` and `required`.

Example of a correct schema:

```python
input_schema = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query"}
    },
    "required": ["query"]
}
```

If a schema is invalid, hivemind raises a validation error at registration time. Run with `HIVEMIND_DEBUG=1` to see the full error detail.

## Version Conflicts

If your plugin depends on a library version that conflicts with hivemind's own dependencies, pip will report a conflict during installation. To diagnose:

```bash
pip check
```

Resolve conflicts by relaxing version constraints in your plugin's `pyproject.toml`, or by using a compatible version range.

## Reading `hivemind doctor` Output

`hivemind doctor` prints a diagnostic report including:

- **Runtime version** -- the installed hivemind version.
- **Loaded plugins** -- each discovered entry point and its load status.
- **Registered tools** -- all tools in the registry, grouped by category.
- **Configuration** -- active `[tools]` settings including `enabled` and `top_k`.

A plugin marked as `FAILED` in the output means it was discovered but could not be loaded. Re-run with `HIVEMIND_DEBUG=1` for the full error.

## Debugging Tips

### Enable Debug Logging

Set the `HIVEMIND_DEBUG` environment variable to get verbose output:

```bash
HIVEMIND_DEBUG=1 hivemind doctor
```

### Inspect Entry Points Manually

You can verify that your entry point is discoverable by Python's packaging metadata:

```python
from importlib.metadata import entry_points

eps = entry_points(group="hivemind.plugins")
for ep in eps:
    print(ep.name, ep.value)
```

### Test Your Tool in Isolation

Import and invoke your tool directly to rule out registry issues:

```python
from my_plugin.tools import MyTool

tool = MyTool()
result = tool.run(query="test")
print(result)
```

## Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `No entry point found for 'my_plugin'` | Entry point name or group is wrong | Check `pyproject.toml` entry point group is `hivemind.plugins` |
| `ModuleNotFoundError: No module named 'my_plugin'` | Package not installed or wrong module path | Run `pip install -e .` and verify module path |
| `Tool 'x' already registered` | Duplicate tool name across plugins | Rename your tool to use a unique `name` |
| `Schema validation failed` | Invalid JSON Schema in `input_schema` | Validate your schema against the JSON Schema spec |
| `TypeError: run() got an unexpected keyword argument` | `run()` signature doesn't match `input_schema` | Ensure `run(**kwargs)` accepts all declared properties |

## Further Resources

- [Plugin Quickstart](/docs/plugins/quickstart) -- build your first plugin in 5 minutes.
- [Plugin Examples](/docs/plugins/examples) -- complete working plugin code.
- [Publishing Plugins](/docs/plugins/publishing) -- share your plugin with others.
