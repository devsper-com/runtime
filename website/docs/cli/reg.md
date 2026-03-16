---
title: "devsper reg"
---

# devsper reg

Quick reference for all `devsper reg` subcommands. These commands manage plugins through the [devsper registry](/docs/cli/registry).

## Subcommands

| Subcommand | Synopsis | Description |
|------------|----------|-------------|
| `install` | `devsper reg install <package>` | Install a plugin from the registry |
| `search` | `devsper reg search <query>` | Search the registry for plugins |
| `publish` | `devsper reg publish` | Publish the current package to the registry |
| `info` | `devsper reg info <package>` | Show plugin metadata and versions |
| `login` | `devsper reg login` | Authenticate with the registry |

## Examples

### install

```bash
devsper reg install devsper-web-scraper
devsper reg install devsper-pdf-reader@1.2.0
```

### search

```bash
devsper reg search "web"
devsper reg search "database"
```

### publish

```bash
devsper reg publish
```

Reads `pyproject.toml` from the current directory, builds the package, and uploads it. Requires prior authentication via `devsper reg login`.

### info

```bash
devsper reg info devsper-web-scraper
```

Displays the package description, available versions, author, and dependencies.

### login

```bash
devsper reg login
```

Authenticates with the registry and stores a token at `~/.config/devsper/registry_token`.

## Common Workflows

### Search, install, and use a plugin

```bash
devsper reg search "pdf"
devsper reg install devsper-pdf-reader
devsper doctor                           # verify plugin loaded
devsper run "summarize report.pdf"
```

### Author, test, and publish a plugin

```bash
# develop locally
pip install -e ./devsper-my-plugin
devsper doctor                           # verify tool loads

# authenticate and publish
devsper reg login
devsper reg publish

# verify in registry
devsper reg info devsper-my-plugin
```

### Update an installed plugin

```bash
devsper reg install devsper-web-scraper    # installs latest version
```

## Global Flags

All `devsper reg` subcommands support the standard global flags:

```bash
devsper --debug reg install <package>     # verbose output
devsper --json reg search <query>         # JSON output
devsper --quiet reg install <package>     # minimal output
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
- [CLI overview](/docs/cli/overview) — all devsper commands
