---
title: Registry Overview
---

# Registry Overview

The devsper plugin registry is a package registry for distributing and installing devsper plugins. It serves a similar role to PyPI for Python or npm for Node.js, but is purpose-built for the devsper ecosystem. Plugins published to the registry can be discovered, installed, and managed through both the web interface and the CLI.

The public registry is hosted at [registry.devsper.com](https://registry.devsper.com).

## Architecture

The registry is composed of four services:

- **API** -- A Go application (`registry/api/`) built with [chi](https://github.com/go-chi/chi). Handles all package CRUD, uploads, search, authentication, and serves the [PEP 503](https://peps.python.org/pep-0503/) Simple Repository API for `pip`/`uv` compatibility.
- **Web** -- A React/Vite application (`registry/web/`) that provides the browser-based UI for browsing plugins, managing accounts, and creating API keys. Authentication is handled via [Better Auth](https://better-auth.com/) with GitHub and Google OAuth support.
- **PostgreSQL** -- Stores all package metadata, user accounts, API keys, organizations, download events, and audit logs.
- **Caddy** -- Reverse proxy that terminates TLS, routes `/api/*` and `/simple/*` to the API service, and everything else to the web frontend.

All four services are defined in `registry/docker-compose.prod.yml` and deployed together on a single EC2 instance.

## How Plugins Are Stored

When a plugin is published, the built distribution files (`.whl` or `.tar.gz`) are uploaded to S3. The registry stores metadata (name, version, description, keywords, SHA-256 checksums) in PostgreSQL. Downloads are served via S3 presigned URLs or CloudFront.

Package names are normalized according to [PEP 503](https://peps.python.org/pep-0503/) -- all lowercase, with underscores, dots, and hyphens collapsed to hyphens.

## Public vs. Authenticated Access

The registry uses a split access model:

| Operation | Authentication |
|---|---|
| Browse, search, view packages | Public (no auth required) |
| Install packages via `pip` or `uv` | Public |
| Publish a package | Requires login |
| Yank or delete a version | Requires login (owner only) |
| Manage API keys | Requires login |

Authentication is handled through Bearer tokens (JWT via Better Auth) or API keys passed in the `X-API-Key` header. The CLI stores credentials in your OS keychain.

## CLI Integration

The `devsper reg` command provides full access to registry operations from your terminal:

```bash
# Authenticate with the registry
devsper reg login

# Search for plugins
devsper reg search "web scraping"

# View plugin details
devsper reg info devsper-plugin-example

# List versions of a plugin
devsper reg versions devsper-plugin-example

# Install a plugin (uses pip under the hood)
devsper reg install devsper-plugin-example

# Publish your plugin
devsper reg publish

# Yank a published version
devsper reg yank devsper-plugin-example 0.1.0 --reason "critical bug"
```

## Installing Plugins

Plugins from the registry can be installed using `pip` or `uv` directly, since the registry exposes a PEP 503-compatible Simple Repository API:

```bash
pip install --index-url https://registry.devsper.com/simple/ devsper-plugin-example
```

Or use the CLI shorthand:

```bash
devsper reg install devsper-plugin-example
```

## Features

- **Full-text search** with PostgreSQL `tsvector` indexing
- **Version management** with semantic versioning support
- **Package verification** -- uploaded plugins are verified before publishing
- **Download tracking** with per-file and per-package counters
- **Organization namespaces** for team-owned plugins
- **Audit logging** for all authenticated actions
- **PEP 503 compatibility** so `pip` and `uv` can install directly

## Next Steps

- [Publishing to the Registry](/docs/registry/publishing) -- how to prepare and publish your plugin
- [API Reference](/docs/registry/api-reference) -- full HTTP API documentation
- [Self-hosting the Registry](/docs/self-hosting/registry) -- run your own instance
