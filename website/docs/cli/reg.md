---
title: "hivemind reg"
---

# hivemind reg

Quick reference for all `hivemind reg` subcommands. These commands manage plugins through the [hivemind registry](/docs/cli/registry).

## Subcommands

| Subcommand | Synopsis | Description |
|------------|----------|-------------|
| `install` | `hivemind reg install <package>` | Install a plugin from the registry |
| `search` | `hivemind reg search <query>` | Search the registry for plugins |
| `publish` | `hivemind reg publish` | Publish the current package to the registry |
| `info` | `hivemind reg info <package>` | Show plugin metadata and versions |
| `login` | `hivemind reg login` | Authenticate with the registry |

## Examples

### install

```bash
hivemind reg install hivemind-web-scraper
hivemind reg install hivemind-pdf-reader@1.2.0
```

### search

```bash
hivemind reg search "web"
hivemind reg search "database"
```

### publish

```bash
hivemind reg publish
```

Reads `pyproject.toml` from the current directory, builds the package, and uploads it. Requires prior authentication via `hivemind reg login`.

### info

```bash
hivemind reg info hivemind-web-scraper
```

Displays the package description, available versions, author, and dependencies.

### login

```bash
hivemind reg login
```

Authenticates with the registry and stores a token at `~/.config/hivemind/registry_token`.

## Common Workflows

### Search, install, and use a plugin

```bash
hivemind reg search "pdf"
hivemind reg install hivemind-pdf-reader
hivemind doctor                           # verify plugin loaded
hivemind run "summarize report.pdf"
```

### Author, test, and publish a plugin

```bash
# develop locally
pip install -e ./hivemind-my-plugin
hivemind doctor                           # verify tool loads

# authenticate and publish
hivemind reg login
hivemind reg publish

# verify in registry
hivemind reg info hivemind-my-plugin
```

### Update an installed plugin

```bash
hivemind reg install hivemind-web-scraper    # installs latest version
```

## Global Flags

All `hivemind reg` subcommands support the standard global flags:

```bash
hivemind --debug reg install <package>     # verbose output
hivemind --json reg search <query>         # JSON output
hivemind --quiet reg install <package>     # minimal output
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (network failure, invalid input) |
| `2` | Authentication required or token expired |
| `3` | Package not found |
| `4` | Version conflict or dependency error |

## Related

- [Registry reference](/docs/cli/registry) — full registry documentation
- [Plugin management](/docs/cli/plugins) — installing, configuring, and developing plugins
- [CLI overview](/docs/cli/overview) — all hivemind commands
