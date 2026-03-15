---
title: Publishing
---

# Publishing to the Registry

This guide covers how to prepare, validate, and publish a hivemind plugin to the registry.

## Prerequisites

Before publishing, you need:

1. A hivemind registry account. Sign up at [registry.hivemind.rithul.dev](https://registry.hivemind.rithul.dev) using GitHub or Google OAuth.
2. The `hivemind` CLI installed.
3. A Python build tool -- either `build` (`pip install build`) or `uv`.

## Plugin Structure

A publishable hivemind plugin is a standard Python package with a `pyproject.toml` that declares a `hivemind.plugins` entry point. The registry enforces the following requirements:

- Package name should follow the `hivemind-plugin-*` naming convention
- Names are normalized per PEP 503 (lowercase, hyphens)
- Maximum name length: 128 characters
- Versions must follow PEP 440 format (e.g., `1.0.0`, `0.2.1a1`)

### Minimal pyproject.toml

```toml
[project]
name = "hivemind-plugin-example"
version = "0.1.0"
description = "An example hivemind plugin"
requires-python = ">=3.12"
license = "MIT"
keywords = ["hivemind", "plugin"]

[project.urls]
Homepage = "https://github.com/you/hivemind-plugin-example"
Repository = "https://github.com/you/hivemind-plugin-example"

[project.entry-points."hivemind.plugins"]
example = "hivemind_plugin_example:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

The entry point function (`register` in this example) should return a list of `Tool` objects or tool name strings, or `None` if the plugin self-registers.

## Authentication

Log in to the registry using the device authorization flow:

```bash
hivemind reg login
```

This opens your browser to authorize the CLI. Once approved, the token is stored in your OS keychain. You can verify your identity with:

```bash
hivemind reg whoami
```

For CI environments, set the `HIVEMIND_API_KEY` environment variable instead of using the interactive login flow.

## Validating Your Plugin

Before publishing, run the validation checks:

```bash
hivemind reg test
```

This verifies:

- `pyproject.toml` exists and is valid
- The `hivemind.plugins` entry point is declared
- Required fields are present (version, description, license)
- `requires-python` allows Python 3.12+
- The entry point loads without errors
- Each returned `Tool` object has `name`, `description`, and `run()` attributes

Fix any failures before proceeding.

## Publishing

Once validation passes:

```bash
hivemind reg publish
```

This command:

1. Runs `hivemind reg test` automatically
2. Builds the package (using `python -m build` or `uv build`)
3. Creates the package on the registry if it does not exist yet
4. Uploads the `.whl` and `.tar.gz` distribution files
5. Waits for server-side verification to complete

If the build artifacts already exist, skip the build step:

```bash
hivemind reg publish --skip-build
```

To preview what would be uploaded without actually publishing:

```bash
hivemind reg publish --dry-run
```

### What Happens Server-Side

When you upload a distribution file, the API:

1. Validates the package name and version format
2. Checks the file extension (only `.whl` and `.tar.gz` are accepted)
3. Validates `.whl` files are valid ZIP archives
4. Uploads the file to S3
5. Records the file metadata and SHA-256 checksum in the database
6. Runs verification (checks the plugin loads correctly and exposes valid tools)
7. Publishes the version to the Simple index once verification passes

## Updating an Existing Plugin

To publish a new version, bump the `version` field in your `pyproject.toml` and run `hivemind reg publish` again. The registry does not allow overwriting an existing version -- you must increment the version number.

```toml
[project]
version = "0.2.0"  # bumped from 0.1.0
```

## Yanking a Version

If a published version has a critical issue, you can yank it. Yanked versions are hidden from the Simple index but remain downloadable by pinned version for existing users:

```bash
hivemind reg yank hivemind-plugin-example 0.1.0 --reason "security vulnerability"
```

Only the package owner can yank versions.

## PyPI as an Alternative

Since hivemind plugins are standard Python packages, you can also publish them to PyPI using [twine](https://twine.readthedocs.io/) or your preferred tool. Users can then install with plain `pip install`. The hivemind registry is preferred for discoverability and ecosystem integration, but PyPI works as a complement -- especially for plugins that are also useful outside the hivemind runtime.

## Best Practices

- **Write a good description.** The `description` field is indexed for full-text search.
- **Use keywords.** Add relevant keywords in `pyproject.toml` so users can find your plugin.
- **Include a README.** The web UI displays the README from your package.
- **Pin hivemind compatibility.** Use the `requires-hivemind` field in your pyproject metadata if your plugin depends on a specific runtime version.
- **Test before publishing.** Always run `hivemind reg test` first.
- **Use semantic versioning.** Follow semver conventions so users know what to expect from version bumps.
- **Set up URLs.** Include `Homepage` and `Repository` in `[project.urls]` so users can find your source code and documentation.

## Next Steps

- [Registry API Reference](/docs/registry/api-reference) -- programmatic access to the registry
- [Registry Overview](/docs/registry/overview) -- architecture and features
