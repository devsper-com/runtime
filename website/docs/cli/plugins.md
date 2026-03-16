---
title: "CLI: plugins"
---

# devsper plugins

Plugins extend devsper with additional tools, memory backends, and agent capabilities. They are distributed through the devsper plugin registry and managed with the `devsper reg` command.

## Installing Plugins

Install a plugin from the registry:

```bash
devsper reg install <package>
```

For example:

```bash
devsper reg install devsper-web-scraper
devsper reg install devsper-pdf-reader
```

Plugins are installed into your Python environment alongside devsper.

## Searching for Plugins

Find plugins in the registry by keyword:

```bash
devsper reg search <query>
```

```bash
devsper reg search "pdf"
devsper reg search "database"
```

## Publishing a Plugin

Package and publish your own plugin to the registry:

```bash
devsper reg publish
```

This reads your project metadata and uploads the package. You must be authenticated first (see [registry authentication](/docs/cli/registry)).

## Plugin Details

View metadata, version history, and dependencies for a plugin:

```bash
devsper reg info <package>
```

```bash
devsper reg info devsper-web-scraper
```

## Authentication

Log in to the registry before publishing:

```bash
devsper reg login
```

This stores an authentication token locally for future registry operations.

## Verifying Plugins

After installing plugins, verify they load correctly:

```bash
devsper doctor
```

The doctor output includes a tool count and lists loaded plugins. If a plugin fails to load, doctor reports the error with details.

```
Tools:     12 loaded (2 from plugins)
Plugins:   devsper-web-scraper (v1.2.0), devsper-pdf-reader (v0.9.1)
```

## Managing Installed Plugins

List installed plugins by checking the doctor output or by listing enabled tools in your config. To remove a plugin, uninstall it from your Python environment:

```bash
pip uninstall devsper-web-scraper
```

Then remove it from your `devsper.toml` if it was explicitly listed:

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

A devsper plugin is a Python package that exposes tools through entry points. The minimal structure:

```
devsper-my-plugin/
  pyproject.toml
  devsper_my_plugin/
    __init__.py
    tools.py
```

Register your tools in `pyproject.toml`:

```toml
[project.entry-points."devsper.tools"]
my_tool = "devsper_my_plugin.tools:MyTool"
```

Test locally by installing in development mode:

```bash
pip install -e ./devsper-my-plugin
devsper doctor
```

When ready, publish with `devsper reg publish`. See the [registry reference](/docs/cli/registry) for full details.
