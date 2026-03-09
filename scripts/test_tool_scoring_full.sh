#!/usr/bin/env bash
# Full test: unit tests + CLI commands. Optionally seed DB first with scripts/seed_tool_scores.py.
# Run from project root: ./scripts/test_tool_scoring_full.sh

set -e

echo "=== 1. Unit tests ==="
uv run python -m pytest tests/test_tool_scoring.py -v --tb=short

echo ""
echo "=== 2. hivemind tools ==="
uv run hivemind tools

echo ""
echo "=== 3. hivemind tools --category research ==="
uv run hivemind tools --category research

echo ""
echo "=== 4. hivemind tools --poor ==="
uv run hivemind tools --poor

echo ""
echo "=== 5. hivemind doctor ==="
uv run hivemind doctor

echo ""
echo "=== 6. hivemind analytics ==="
uv run hivemind analytics

echo ""
echo "=== Done: full CLI test passed ==="
