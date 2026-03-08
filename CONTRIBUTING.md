# Contributing to Hivemind

Thank you for your interest in contributing.

## How to contribute

- **Bug reports and feature requests:** Open an [issue](https://github.com/rithulkamesh/hivemind/issues).
- **Code changes:** Open a pull request. Keep changes focused and ensure tests pass.

## Setup instructions

```bash
git clone https://github.com/rithulkamesh/hivemind.git
cd hivemind
uv sync
```

If you use pip: `pip install -e .` and install dev dependencies (pytest, ruff, black, mypy) as needed.

## Testing instructions

```bash
uv run python -m pytest tests/ -v
```

Run a subset: `uv run python -m pytest tests/test_swarm.py -v`

## Code style guidelines

- **Python:** 3.12+
- **Formatting:** Black (`black hivemind examples`)
- **Linting:** Ruff (`ruff check hivemind examples`)
- Follow existing patterns in the codebase (e.g. type hints, docstrings for public APIs).

## PR guidelines

- Keep PRs focused (one feature or fix when possible).
- Ensure all tests pass and lint/format checks succeed.
- Update docs under `docs/` if you change user-facing behavior or add features.
- For new tools or providers, add a short note in the relevant doc (e.g. [tools.md](docs/tools.md), [providers.md](docs/providers.md)).

## Adding tools or features

- **New tool:** See [Tools](docs/tools.md) and [Development — Adding new tools](docs/development.md#adding-new-tools). Add the tool under the right category and register it; add tests in `tests/tools/` if appropriate.
- **New provider:** See [Development — Adding providers](docs/development.md#adding-providers). Implement the provider, wire it in the router, and document config.
- **New example:** Add a script under `examples/` and document it in [Examples](docs/examples.md). Prefer using the shared `examples._common` and `examples._config` helpers.
