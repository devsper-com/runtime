---
title: "CLI: registry"
---

# devsper registry

The devsper plugin registry at **registry.devsper.com** is the central repository for discovering, installing, and publishing devsper plugins. All registry operations use the `devsper reg` subcommand.

## Overview

The registry hosts community and official plugins that extend devsper with additional tools, memory backends, and integrations. Plugins are versioned, searchable, and verified before listing.

## Installing Plugins

Download and install a plugin by name:

```bash
devsper reg install <package>
```

```bash
devsper reg install devsper-web-scraper
devsper reg install devsper-pdf-reader@1.2.0   # pin a specific version
```

Installed plugins are immediately available to the swarm. Run `devsper doctor` to confirm.

## Publishing Plugins

Publish your plugin package to the registry:

```bash
devsper reg publish
```

This command reads your `pyproject.toml` metadata, builds the package, and uploads it to the registry. Requirements:

- You must be authenticated (see below).
- The package must have a valid `pyproject.toml` with name, version, and description.
- Entry points must be declared under `devsper.tools` or another supported namespace.

To update a published plugin, increment the version in `pyproject.toml` and run `devsper reg publish` again.

## Searching Plugins

Search the registry by keyword:

```bash
devsper reg search <query>
```

```bash
devsper reg search "web"
devsper reg search "database connector"
```

Results include package name, latest version, and a short description.

## Authentication and Tokens

Publishing requires authentication. Log in with:

```bash
devsper reg login
```

This opens an authentication flow and stores a token locally at `~/.config/devsper/registry_token`. The token is used automatically for subsequent `publish` and authenticated API calls.

To check your authentication status:

```bash
devsper reg info --me
```

## Registry API

The registry API is available at:

```
https://registry.devsper.com/api/v1/
```

Key endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/packages` | GET | List packages (supports `?q=` search) |
| `/api/v1/packages/<name>` | GET | Package metadata and versions |
| `/api/v1/packages/<name>/download` | GET | Download package artifact |
| `/api/v1/packages` | POST | Publish a new package (auth required) |

The CLI handles all API interaction. Direct API access is available for tooling and CI integrations.

## Troubleshooting

### Connection Errors

If `devsper reg` commands fail to connect:

1. Check network connectivity to `registry.devsper.com`.
2. Verify no proxy or firewall is blocking HTTPS traffic on port 443.
3. Run with `--debug` for detailed request logs:

```bash
devsper --debug reg search "test"
```

### Authentication Failures

If publish fails with a 401 or 403 error:

1. Re-authenticate with `devsper reg login`.
2. Delete the cached token and log in again:

```bash
rm ~/.config/devsper/registry_token
devsper reg login
```

### Package Not Found

If `devsper reg install` reports a package as not found:

1. Verify the package name with `devsper reg search`.
2. Check for typos in the package name.
3. The package may have been unpublished by its author.

### Version Conflicts

If an installed plugin conflicts with your devsper version:

```bash
pip install --upgrade devsper
devsper reg install <package>
```

Ensure your devsper installation meets the plugin's declared version requirements.

See also: [devsper reg quick reference](/docs/cli/reg), [plugin management](/docs/cli/plugins).
