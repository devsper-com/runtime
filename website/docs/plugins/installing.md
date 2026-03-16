---
title: Installing Plugins
---

# Installing Plugins

Plugins are standard Python packages. You can install them from PyPI, the devsper plugin registry, or directly from a Git repository.

## From PyPI

The simplest method. Plugin packages follow the naming convention `devsper-plugin-<name>`:

```bash
pip install devsper-plugin-<name>
```

For example:

```bash
pip install devsper-plugin-demo
```

If you use `uv` for dependency management:

```bash
uv pip install devsper-plugin-<name>
```

## From the devsper registry

The devsper plugin registry at [registry.devsper.com](https://registry.devsper.com) hosts verified plugins. Install from it using pip's `--index-url` option:

```bash
pip install --index-url https://registry.devsper.com/simple/ devsper-plugin-<name>
```

You can also browse and search the registry from the CLI:

```bash
devsper reg search <query>
devsper reg info <package>
```

## From Git

Install directly from a Git repository:

```bash
pip install git+https://github.com/<user>/devsper-plugin-<name>.git
```

To pin a specific branch, tag, or commit:

```bash
pip install git+https://github.com/<user>/devsper-plugin-<name>.git@v1.0.0
pip install git+https://github.com/<user>/devsper-plugin-<name>.git@main
```

## From a Local Directory

During development, install a plugin in editable mode from a local checkout:

```bash
pip install -e ./path/to/devsper-plugin-<name>
```

This is useful when [authoring a plugin](/docs/plugins/authoring) and testing it against your devsper installation.

## Verifying Installation

After installing a plugin, verify it loaded correctly:

```bash
devsper doctor
```

The `doctor` command shows diagnostics including which plugins were discovered and loaded. If a plugin fails to load, you will see a warning with the error details.

You can also verify programmatically:

```python
from devsper.plugins.plugin_registry import list_plugins

for plugin in list_plugins():
    print(f"{plugin.name} v{plugin.version}: {plugin.tools_registered}")
```

## Managing Plugins

### List Installed Plugins

All installed plugins that declare a `devsper.plugins` entry point are discovered automatically. To see what is currently loaded:

```python
from devsper.plugins.plugin_registry import list_plugins

for p in list_plugins():
    print(f"{p.name} ({p.version}) - tools: {p.tools_registered}")
```

### Uninstall a Plugin

Since plugins are regular Python packages, uninstall them with pip:

```bash
pip uninstall devsper-plugin-<name>
```

The plugin's tools will no longer be available on the next devsper startup.

### Selective Loading

You can restrict which plugins are loaded by passing an `enabled` list to the plugin loader. This is useful in environments where you want fine-grained control:

```python
from devsper.plugins.plugin_loader import load_plugins

# Only load the "demo" and "web" plugins
load_plugins(enabled=["demo", "web"])
```

When `enabled` is `None` (the default), all discovered plugins are loaded.

## Plugin Compatibility

Plugins depend on `devsper` as a runtime dependency. When installing, ensure version compatibility:

- Check the plugin's `requires-python` field -- devsper requires Python 3.12+
- Check the plugin's `dependencies` for the required `devsper` version
- Use `devsper reg info <package>` to see metadata before installing

If a plugin fails to load due to an incompatible API, the loader logs a warning and continues loading other plugins without crashing.

## Next Steps

- [Authoring Plugins](/docs/plugins/authoring) -- Create your own plugin
- [Hooks and API Reference](/docs/plugins/hooks-api) -- Tool and registry APIs
- [Distribution](/docs/plugins/distribution) -- Publish your plugin
