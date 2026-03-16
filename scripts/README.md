# Scripts for testing and manual verification

## Tool Reliability Scoring (v1.3)

Run from the project root (where `devsper.toml` or `pyproject.toml` lives).

### Quick test (CLI only)

```bash
./scripts/test_tool_scoring_cli.sh
```

- Runs unit tests, then exercises `devsper tools`, `devsper tools --poor`, `devsper doctor`, `devsper analytics`.

### Full test (all CLI commands)

```bash
./scripts/test_tool_scoring_full.sh
```

- Unit tests plus: `devsper tools`, `devsper tools --category research`, `devsper tools --poor`, `devsper doctor`, `devsper analytics`.

### Optional: seed DB for a populated table

```bash
uv run python scripts/seed_tool_scores.py
uv run devsper tools
uv run devsper analytics
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
uv run devsper tools

# CLI: only poor tools
uv run devsper tools --poor

# CLI: by category
uv run devsper tools --category research

# Doctor (includes scoring DB info)
uv run devsper doctor

# Analytics (includes tool report when scores exist)
uv run devsper analytics

# Reset one tool (replace TOOL_NAME)
uv run devsper tools reset TOOL_NAME

# Bypass scoring in selection (env)
DEVSPER_DISABLE_TOOL_SCORING=1 uv run devsper run "list files"
```
