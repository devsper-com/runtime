---
title: "CLI: plugins"
---

# hivemind plugins

Plugins extend hivemind with additional tools, memory backends, and agent capabilities. They are distributed through the hivemind plugin registry and managed with the `hivemind reg` command.

## Installing Plugins

Install a plugin from the registry:

```bash
hivemind reg install <package>
```

For example:

```bash
hivemind reg install hivemind-web-scraper
hivemind reg install hivemind-pdf-reader
```

Plugins are installed into your Python environment alongside hivemind.

## Searching for Plugins

Find plugins in the registry by keyword:

```bash
hivemind reg search <query>
```

```bash
hivemind reg search "pdf"
hivemind reg search "database"
```

## Publishing a Plugin

Package and publish your own plugin to the registry:

```bash
hivemind reg publish
```

This reads your project metadata and uploads the package. You must be authenticated first (see [registry authentication](/docs/cli/registry)).

## Plugin Details

View metadata, version history, and dependencies for a plugin:

```bash
hivemind reg info <package>
```

```bash
hivemind reg info hivemind-web-scraper
```

## Authentication

Log in to the registry before publishing:

```bash
hivemind reg login
```

This stores an authentication token locally for future registry operations.

## Verifying Plugins

After installing plugins, verify they load correctly:

```bash
hivemind doctor
```

The doctor output includes a tool count and lists loaded plugins. If a plugin fails to load, doctor reports the error with details.

```
Tools:     12 loaded (2 from plugins)
Plugins:   hivemind-web-scraper (v1.2.0), hivemind-pdf-reader (v0.9.1)
```

## Managing Installed Plugins

List installed plugins by checking the doctor output or by listing enabled tools in your config. To remove a plugin, uninstall it from your Python environment:

```bash
pip uninstall hivemind-web-scraper
```

Then remove it from your `hivemind.toml` if it was explicitly listed:

```toml
[tools]
enabled = ["web_search", "file_reader"]
```

## Plugin Loading Config

Control which tools (including those from plugins) are available to the swarm:

```toml
[tools]
enabled = ["web_search", "file_reader", "web_scraper"]
top_k = 5
```

- **`enabled`** — list of tool names to load. Omit this field to load all available tools.
- **`top_k`** — maximum number of tools selected per task via smart tool selection.

If `enabled` is set, only the listed tools are loaded. Tools from installed plugins that are not in the list are ignored.

## Plugin Development

A hivemind plugin is a Python package that exposes tools through entry points. The minimal structure:

```
hivemind-my-plugin/
  pyproject.toml
  hivemind_my_plugin/
    __init__.py
    tools.py
```

Register your tools in `pyproject.toml`:

```toml
[project.entry-points."hivemind.tools"]
my_tool = "hivemind_my_plugin.tools:MyTool"
```

Test locally by installing in development mode:

```bash
pip install -e ./hivemind-my-plugin
hivemind doctor
```

When ready, publish with `hivemind reg publish`. See the [registry reference](/docs/cli/registry) for full details.
