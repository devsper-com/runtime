#!/usr/bin/env bash
# Phase 5 — automated QA stabilization checks (unit-level; logs success/failure).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "[qa_e2e_stabilization] Running pytest stabilization + platform event tests..."
.venv/bin/python -m pytest \
  tests/test_platform_runtime_events.py \
  tests/test_execution_graph_meta.py \
  tests/test_model_router.py \
  -q --tb=short
echo "[qa_e2e_stabilization] OK"

echo "[qa_e2e_stabilization] Optional: full swarm (requires credentials) — skipped by default."
echo "  To run: DEVSPER_PROFILE= .venv/bin/python -m devsper.cli.main --plain -q run 'smoke'"
