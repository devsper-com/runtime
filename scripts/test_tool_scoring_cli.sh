#!/usr/bin/env bash
# Quick CLI test for Tool Reliability Scoring (v1.3).
# Run from project root: ./scripts/test_tool_scoring_cli.sh

set -e

echo "=== 1. Unit tests ==="
uv run python -m pytest tests/test_tool_scoring.py -v --tb=short

echo ""
echo "=== 2. hivemind tools (list) ==="
uv run hivemind tools

echo ""
echo "=== 3. hivemind tools --poor ==="
uv run hivemind tools --poor

echo ""
echo "=== 4. hivemind doctor (includes scoring DB info) ==="
uv run hivemind doctor

echo ""
echo "=== 5. hivemind analytics (includes tool report when scores exist) ==="
uv run hivemind analytics

echo ""
echo "=== Done: CLI checks passed ==="
