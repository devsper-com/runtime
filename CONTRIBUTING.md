# Contributing to devsper

Thank you for your interest in contributing.

## How to contribute

- **Bug reports and feature requests:** Open an [issue](https://github.com/devsper-com/runtime/issues).
- **Code changes:** Open a pull request. Keep changes focused and ensure tests pass.

## Setup instructions

```bash
git clone https://github.com/devsper-com/runtime.git
cd devsper
uv sync
```

If you use pip: `pip install -e .` and install dev dependencies (pytest, ruff, black, mypy) as needed.

## Testing instructions

```bash
uv run python -m pytest tests/ -v
```

Run a subset: `uv run python -m pytest tests/test_swarm.py -v`. Version-specific tests: `tests/test_v19.py` (v1.9 serialization, bus, executor, scheduler, checkpointer, health).

## Code style guidelines

- **Python:** 3.12+
- **Formatting:** Black (`black devsper examples`)
- **Linting:** Ruff (`ruff check devsper examples`)
- Follow existing patterns in the codebase (e.g. type hints, docstrings for public APIs).

## PR guidelines

- Keep PRs focused (one feature or fix when possible).
- Ensure all tests pass and lint/format checks succeed.
- Update docs in `website/docs/` if you change user-facing behavior or add features (site: [docs.devsper.com](https://docs.devsper.com)).
- For new tools or providers, add a short note in the relevant doc (e.g. [tools](https://docs.devsper.com/docs/tools), [providers](https://docs.devsper.com/docs/providers)).

## Adding tools or features

- **New tool:** See [Tools](https://docs.devsper.com/docs/tools) and [Development — Adding new tools](https://docs.devsper.com/docs/development#adding-new-tools). Add the tool under the right category and register it; add tests in `tests/tools/` if appropriate.
- **New provider:** See [Development — Adding providers](https://docs.devsper.com/docs/development#adding-providers). Implement the provider, wire it in the router, and document config.
- **New example:** Add a script under `examples/` and document it in [Examples](https://docs.devsper.com/docs/examples). Prefer using the shared `examples._common` and `examples._config` helpers.
