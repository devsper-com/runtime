#!/usr/bin/env bash
# Run distributed demo: Redis + 1 worker + controller.
# From project root: bash examples/distributed/run_demo.sh

set -e
cd "$(dirname "$0")/../.."

echo "1. Starting Redis..."
docker compose up -d
sleep 2

echo "2. Start a worker in another terminal:"
echo "   uv run python examples/distributed/run_worker.py"
echo ""
read -p "Press Enter after the worker is running..."

echo "3. Running controller with a single task..."
uv run python examples/distributed/run_controller.py "Summarize swarm intelligence in one sentence."

echo ""
echo "Done. Stop the worker with Ctrl+C; stop Redis with: docker compose down"
