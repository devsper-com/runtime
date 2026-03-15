---
title: Installing Plugins
---

# Installing Plugins

Plugins are standard Python packages. You can install them from PyPI, the hivemind plugin registry, or directly from a Git repository.

## From PyPI

The simplest method. Plugin packages follow the naming convention `hivemind-plugin-<name>`:

```bash
pip install hivemind-plugin-<name>
```

For example:

```bash
pip install hivemind-plugin-demo
```

If you use `uv` for dependency management:

```bash
uv pip install hivemind-plugin-<name>
```

## From the Hivemind Registry

The hivemind plugin registry at [registry.hivemind.rithul.dev](https://registry.hivemind.rithul.dev) hosts verified plugins. Install from it using pip's `--index-url` option:

```bash
pip install --index-url https://registry.hivemind.rithul.dev/simple/ hivemind-plugin-<name>
```

You can also browse and search the registry from the CLI:

```bash
hivemind reg search <query>
hivemind reg info <package>
```

## From Git

Install directly from a Git repository:

```bash
pip install git+https://github.com/<user>/hivemind-plugin-<name>.git
```

To pin a specific branch, tag, or commit:

```bash
pip install git+https://github.com/<user>/hivemind-plugin-<name>.git@v1.0.0
pip install git+https://github.com/<user>/hivemind-plugin-<name>.git@main
```

## From a Local Directory

During development, install a plugin in editable mode from a local checkout:

```bash
pip install -e ./path/to/hivemind-plugin-<name>
```

This is useful when [authoring a plugin](/docs/plugins/authoring) and testing it against your hivemind installation.

## Verifying Installation

After installing a plugin, verify it loaded correctly:

```bash
hivemind doctor
```

The `doctor` command shows diagnostics including which plugins were discovered and loaded. If a plugin fails to load, you will see a warning with the error details.

You can also verify programmatically:

```python
from hivemind.plugins.plugin_registry import list_plugins

for plugin in list_plugins():
    print(f"{plugin.name} v{plugin.version}: {plugin.tools_registered}")
```

## Managing Plugins

### List Installed Plugins

All installed plugins that declare a `hivemind.plugins` entry point are discovered automatically. To see what is currently loaded:

```python
from hivemind.plugins.plugin_registry import list_plugins

for p in list_plugins():
    print(f"{p.name} ({p.version}) - tools: {p.tools_registered}")
```

### Uninstall a Plugin

Since plugins are regular Python packages, uninstall them with pip:

```bash
pip uninstall hivemind-plugin-<name>
```

The plugin's tools will no longer be available on the next hivemind startup.

### Selective Loading

You can restrict which plugins are loaded by passing an `enabled` list to the plugin loader. This is useful in environments where you want fine-grained control:

```python
from hivemind.plugins.plugin_loader import load_plugins

# Only load the "demo" and "web" plugins
load_plugins(enabled=["demo", "web"])
```

When `enabled` is `None` (the default), all discovered plugins are loaded.

## Plugin Compatibility

Plugins depend on `hivemind-ai` as a runtime dependency. When installing, ensure version compatibility:

- Check the plugin's `requires-python` field -- hivemind requires Python 3.12+
- Check the plugin's `dependencies` for the required `hivemind-ai` version
- Use `hivemind reg info <package>` to see metadata before installing

If a plugin fails to load due to an incompatible API, the loader logs a warning and continues loading other plugins without crashing.

## Next Steps

- [Authoring Plugins](/docs/plugins/authoring) -- Create your own plugin
- [Hooks and API Reference](/docs/plugins/hooks-api) -- Tool and registry APIs
- [Distribution](/docs/plugins/distribution) -- Publish your plugin
