---
title: Publishing Plugins
---

# Publishing Plugins

Once your plugin is working locally, you can share it by publishing to PyPI, the devsper registry, or both.

## Preparing for Publication

Before publishing, ensure your plugin meets these requirements:

### Versioning

Use semantic versioning in `pyproject.toml`. Bump the version for every release:

```toml
[project]
version = "1.0.0"
```

### Package Metadata

Include complete metadata so users can find and evaluate your plugin:

```toml
[project]
name = "devsper-plugin-example"
version = "1.0.0"
description = "A brief description of what your plugin does"
license = {text = "MIT"}
authors = [{name = "Your Name", email = "you@example.com"}]
keywords = ["devsper", "plugin"]
requires-python = ">=3.10"
dependencies = ["devsper"]

[project.urls]
Homepage = "https://github.com/you/devsper-plugin-example"

[project.entry-points."devsper.plugins"]
example = "example_plugin:register_tools"
```

### README

Include a `README.md` that describes the plugin, lists the tools it provides, and shows basic usage. PyPI and the devsper registry both render this file on your package page.

### Tests

Write tests for your tools before publishing. At minimum, verify that each tool's `run()` method returns a string and handles edge cases:

```python
from example_plugin import MyTool

def test_my_tool():
    tool = MyTool()
    result = tool.run(query="test input")
    assert isinstance(result, str)
    assert len(result) > 0
```

Run your tests:

```bash
pytest
```

## Publishing to PyPI

This is the standard Python package publishing workflow.

### Build the Package

```bash
pip install build twine
python -m build
```

This creates distribution files in the `dist/` directory.

### Upload to PyPI

```bash
twine upload dist/*
```

You will be prompted for your PyPI credentials. For automation, configure a PyPI API token.

### Verify on PyPI

After uploading, confirm the package is available:

```bash
pip install devsper-plugin-example
devsper doctor
```

## Publishing to the devsper registry

The devsper registry is a curated index of plugins. Publishing here makes your plugin discoverable via the `devsper reg` CLI.

### Login

Authenticate with the registry:

```bash
devsper reg login
```

### Test Before Publishing

Run a pre-publish check to catch common issues:

```bash
devsper reg test
```

This validates your entry point configuration, schema definitions, and package metadata.

### Publish

```bash
devsper reg publish
```

The command packages your plugin and uploads it to the registry. It requires that the package is already published to PyPI.

### Verify

Search for your plugin to confirm it appears:

```bash
devsper reg search example
```

Users can then install it with:

```bash
devsper reg install devsper-plugin-example
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `devsper reg login` | Authenticate with the devsper registry |
| `devsper reg test` | Validate plugin before publishing |
| `devsper reg publish` | Publish plugin to the registry |
| `devsper reg search <query>` | Search for plugins by name or keyword |
| `devsper reg install <name>` | Install a plugin from the registry |

## Post-Publish Checklist

1. Install the published package in a clean virtual environment.
2. Run `devsper doctor` and confirm your tools are registered.
3. Test the tools end-to-end in a devsper task.
4. Tag the release in your version control system.
5. Update your README if the tool set has changed.

## Updating a Published Plugin

To publish an update, increment the version in `pyproject.toml`, rebuild, and re-upload:

```bash
# Update version in pyproject.toml, then:
python -m build
twine upload dist/*
devsper reg publish
```

## Further Reading

- [Plugin Quickstart](/docs/plugins/quickstart) -- build your first plugin.
- [Plugin Examples](/docs/plugins/examples) -- complete working examples.
- [Troubleshooting](/docs/plugins/troubleshooting) -- diagnose common publishing issues.
