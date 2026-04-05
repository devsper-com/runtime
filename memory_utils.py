"""
Compatibility shim for container smoke tests.

The real implementation lives at `devsper.server.memory_utils`.
This file exists so `from memory_utils import ...` works when
`PYTHONPATH=/app` (where `/app` is mounted `./runtime`).
"""

from devsper.server.memory_utils import *  # noqa: F403

