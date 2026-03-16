#!/usr/bin/env bash
# Quick CLI test for Tool Reliability Scoring (v1.3).
# Run from project root: ./scripts/test_tool_scoring_cli.sh

set -e

echo "=== 1. Unit tests ==="
uv run python -m pytest tests/test_tool_scoring.py -v --tb=short

echo ""
echo "=== 2. devsper tools (list) ==="
uv run devsper tools

echo ""
echo "=== 3. devsper tools --poor ==="
uv run devsper tools --poor

echo ""
echo "=== 4. devsper doctor (includes scoring DB info) ==="
uv run devsper doctor

echo ""
echo "=== 5. devsper analytics (includes tool report when scores exist) ==="
uv run devsper analytics

echo ""
echo "=== Done: CLI checks passed ==="
