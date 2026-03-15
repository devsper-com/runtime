---
title: Distribution
---

# Distributing Plugins

Once you have authored a plugin, you can distribute it through PyPI, the hivemind plugin registry, or both.

## Package Naming

Follow the convention `hivemind-plugin-<name>` for your distribution name. This makes plugins discoverable and establishes them as part of the hivemind ecosystem.

```
hivemind-plugin-web-search
hivemind-plugin-slack
hivemind-plugin-postgres
```

The Python package (import name) uses underscores: `hivemind_plugin_web_search`.

## Publishing to PyPI

Standard Python packaging workflow:

```bash
# Install build tools
pip install build twine

# Build the distribution
python -m build

# Upload to PyPI
twine upload dist/*
```

Or with `uv`:

```bash
uv build
uv publish
```

Users install your plugin with:

```bash
pip install hivemind-plugin-<name>
```

## Publishing to the Hivemind Registry

The hivemind registry at [registry.hivemind.rithul.dev](https://registry.hivemind.rithul.dev) provides plugin-specific features like server-side verification and tool discovery.

### Authenticate

Log in using the device flow:

```bash
hivemind reg login
```

This opens your browser for authorization and stores the API key in your OS keychain. For CI environments, set the `HIVEMIND_API_KEY` environment variable instead.

### Validate

Before publishing, validate your plugin passes all checks:

```bash
hivemind reg test
```

This verifies:

- `pyproject.toml` exists with required fields (version, description, license)
- `hivemind.plugins` entry point is declared
- `requires-python` allows 3.12+
- Entry point loads without error and returns valid `Tool` objects

### Publish

Build and upload in one step:

```bash
hivemind reg publish
```

The `publish` command runs validation, builds the package (using `python -m build` or `uv build`), uploads the distribution files, and waits for server-side verification to complete.

Options:

- `--dir <path>` -- Publish from a different directory (default: current directory)
- `--skip-build` -- Upload existing files from `dist/` without rebuilding
- `--dry-run` -- Show what would be uploaded without actually publishing

### Verify Your Account

Check your login status:

```bash
hivemind reg whoami
```

### Search the Registry

```bash
hivemind reg search "web scraping"
hivemind reg search --verified "data"
```

### View Package Details

```bash
hivemind reg info hivemind-plugin-<name>
hivemind reg versions hivemind-plugin-<name>
```

### Yank a Release

If a version has a critical issue, yank it to prevent new installs:

```bash
hivemind reg yank hivemind-plugin-<name> 0.1.0 --reason "Critical bug in tool output"
```

Yanked versions are still available to existing dependents but hidden from new installs.

## Versioning Strategy

Follow [Semantic Versioning](https://semver.org/):

- **Patch** (0.1.1) -- Bug fixes, no API changes
- **Minor** (0.2.0) -- New tools added, backward-compatible changes
- **Major** (1.0.0) -- Breaking changes to tool names, schemas, or behavior

The registry rejects uploads with duplicate version numbers. Bump the version in `pyproject.toml` before each publish.

## Dependencies and Compatibility

### Runtime Dependency

Your plugin must depend on `hivemind-ai`:

```toml
[project]
dependencies = [
    "hivemind-ai",
]
```

Pin to a compatible range if your plugin relies on specific APIs:

```toml
dependencies = [
    "hivemind-ai>=0.9,<1.0",
]
```

### Python Version

Hivemind requires Python 3.12+. Set `requires-python` accordingly:

```toml
requires-python = ">=3.12"
```

### External Dependencies

Keep external dependencies minimal. If your plugin requires heavy libraries (e.g., ML frameworks), document them clearly and consider making them optional.

## README and Documentation

Include a `README.md` that covers:

- What the plugin does and which tools it provides
- Installation instructions
- Example usage of each tool
- Configuration requirements (API keys, environment variables)
- License

The registry reads package metadata from `pyproject.toml` -- ensure `description`, `license`, and `version` are populated.

## Checklist

Before publishing, verify:

1. Package name follows `hivemind-plugin-<name>` convention
2. `pyproject.toml` has version, description, license, and entry point
3. `requires-python = ">=3.12"` is set
4. `hivemind-ai` is listed as a dependency
5. `hivemind reg test` passes all checks
6. README documents the tools and their usage
7. Version has been bumped since the last release

## Next Steps

- [Plugin Overview](/docs/plugins/overview) -- Architecture and lifecycle
- [Authoring Plugins](/docs/plugins/authoring) -- Creating plugins from scratch
- [Hooks and API Reference](/docs/plugins/hooks-api) -- Full API documentation
