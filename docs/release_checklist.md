# OSS Release Checklist

Use this checklist before tagging a release or publishing to PyPI.

## Pre-release

- [ ] **Tests passing** — `uv run python -m pytest tests/ -v` (or `pytest tests/ -v`) completes with no failures.
- [ ] **Examples working** — Run at least:
  - `hivemind run "Summarize swarm intelligence in one paragraph."`
  - `hivemind research .` or `hivemind analyze .` (if examples dir exists)
  - `uv run python examples/experiments/parameter_sweep.py --params '{"lr":[0.01]}'`
- [ ] **Docs complete** — All files under `docs/` are present and up to date (introduction, architecture, swarm_runtime, tools, memory_system, providers, cli, tui, examples, development, contributing, faq, release_checklist).
- [ ] **CLI working** — `hivemind run "task"`, `hivemind tui`, `hivemind research path`, `hivemind analyze path`, `hivemind memory --limit 5` behave as documented.
- [ ] **TUI working** — `hivemind tui` starts; prompt + run + dashboard (d) work; no regressions.

## Packaging

- [ ] **PyPI packaging configured** — `pyproject.toml` has correct `name` (e.g. `hivemind-ai`), `version`, `requires-python`, dependencies, and `[project.scripts]` for `hivemind`.
- [ ] **Version bumped** — Set or bump `version` in `pyproject.toml` for the release (e.g. `0.1.1`).

## GitHub release steps

1. Commit all changes and push to the default branch.
2. Create a new **GitHub release** with tag `vX.Y.Z` (e.g. `v0.1.1`) and release notes (e.g. from `CHANGELOG.md`).
3. If using GitHub Actions for PyPI: ensure **Trusted Publishing** (or token) is configured so the workflow can publish the package.
4. Trigger or wait for the publish workflow (e.g. on `release: published` or tag push).

## Post-release

- [ ] Verify the package is installable: `pip install hivemind-ai` and `hivemind --help`.
- [ ] Update `CHANGELOG.md` with the release date and any last-minute notes.
