#!/bin/bash
set -e

# trulens-core pins rich>=13.6,<14 which conflicts with devsper's rich>=14.3.3.
# We override the constraint via a temp file — rich 14.x is backward-compatible
# with the Console/Table APIs trulens uses.

OVERRIDE=$(mktemp)
echo "rich>=14.3.3" > "$OVERRIDE"

uv tool uninstall devsper 2>/dev/null || true
uv tool install ".[trulens]" --override "$OVERRIDE"

rm -f "$OVERRIDE"
