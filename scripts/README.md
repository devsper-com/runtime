# Scripts for testing and manual verification

## Tool Reliability Scoring (v1.3)

Run from the project root (where `hivemind.toml` or `pyproject.toml` lives).

### Quick test (CLI only)

```bash
./scripts/test_tool_scoring_cli.sh
```

- Runs unit tests, then exercises `hivemind tools`, `hivemind tools --poor`, `hivemind doctor`, `hivemind analytics`.

### Full test (all CLI commands)

```bash
./scripts/test_tool_scoring_full.sh
```

- Unit tests plus: `hivemind tools`, `hivemind tools --category research`, `hivemind tools --poor`, `hivemind doctor`, `hivemind analytics`.

### Optional: seed DB for a populated table

```bash
uv run python scripts/seed_tool_scores.py
uv run hivemind tools
uv run hivemind analytics
```

### Python smoke test

```bash
uv run python scripts/test_tool_scoring_smoke.py
```

- Uses a temporary DB: records results, checks composite score and labels, selector blend, reset, prune. No CLI.

### One-liners (copy-paste)

```bash
# Unit tests only
uv run python -m pytest tests/test_tool_scoring.py -v

# CLI: list tools (scores if any)
uv run hivemind tools

# CLI: only poor tools
uv run hivemind tools --poor

# CLI: by category
uv run hivemind tools --category research

# Doctor (includes scoring DB info)
uv run hivemind doctor

# Analytics (includes tool report when scores exist)
uv run hivemind analytics

# Reset one tool (replace TOOL_NAME)
uv run hivemind tools reset TOOL_NAME

# Bypass scoring in selection (env)
HIVEMIND_DISABLE_TOOL_SCORING=1 uv run hivemind run "list files"
```
