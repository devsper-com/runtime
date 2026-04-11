#!/bin/bash
set -e

# trulens-core pins rich>=13.6,<14 which is incompatible with devsper's
# rich>=14.3.3.  Install the base tool first, then inject trulens-core into
# the isolated tool env using --override so uv forces rich>=14.3.3.
# rich 14.x is backward-compatible with the Console/Table APIs trulens uses.

uv tool uninstall devsper 2>/dev/null || true
uv tool install .

# Inject trulens-core post-install (override the rich pin)
OVERRIDE=$(mktemp)
echo "rich>=14.3.3" > "$OVERRIDE"
uv tool install . --with "trulens-core>=1.0" --override "$OVERRIDE" 2>/dev/null \
    && echo "  trulens-core installed (TruLens observability enabled)" \
    || echo "  [warn] trulens-core skipped — run 'pip install trulens-core' manually"
rm -f "$OVERRIDE"
