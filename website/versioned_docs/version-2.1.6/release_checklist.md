# OSS Release Checklist

Use this checklist before tagging a release or publishing to PyPI.

## Pre-release

- [ ] **Tests passing** — `uv run python -m pytest tests/ -v` (or `pytest tests/ -v`) completes with no failures.
- [ ] **Examples working** — Run at least:
  - `devsper run "Summarize swarm intelligence in one paragraph."`
  - `devsper research .` or `devsper analyze .` (if examples dir exists)
  - `uv run python examples/experiments/parameter_sweep.py --params '{"lr":[0.01]}'`
- [ ] **Docs complete** — All files under `docs/` are present and up to date (introduction, architecture, swarm_runtime, tools, memory_system, providers, cli, tui, examples, development, contributing, faq, release_checklist).
- [ ] **CLI working** — `devsper run "task"`, `devsper tui`, `devsper research path`, `devsper analyze path`, `devsper memory --limit 5` behave as documented.
- [ ] **TUI working** — `devsper tui` starts; prompt + run + dashboard (d) work; no regressions.

## Packaging

- [ ] **PyPI packaging configured** — `pyproject.toml` has correct `name` (e.g. `devsper`), `version`, `requires-python`, dependencies, and `[project.scripts]` for `devsper`.
- [ ] **Version bumped** — Set or bump `version` in `pyproject.toml` for the release (e.g. `0.1.1`).

## GitHub release steps

1. Commit all changes and push to the default branch.
2. Create a new **GitHub release** with tag `vX.Y.Z` (e.g. `v0.1.1`) and release notes (e.g. from `CHANGELOG.md`).
3. **Trusted Publishing (PyPI):** Add this repo as a Trusted Publisher on PyPI (project **devsper**, workflow **pypi-publish.yml**). The publisher will show as "Pending" until the first successful run; publishing a release triggers the workflow and completes verification.
4. The **Publish to PyPI** workflow runs on `release: published` and uploads the package (no API token needed when Trusted Publishing is used).

## Post-release

- [ ] Verify the package is installable: `pip install devsper` and `devsper --help`.
- [ ] Update `CHANGELOG.md` with the release date and any last-minute notes.
- [ ] **Website release notes** — Copy the new release section from `CHANGELOG.md` into `website/docs/release_notes.md` (move **Unreleased** into `[X.Y.Z]` and update the hero pill version on the home page in `website/src/pages/index.js` if needed).
