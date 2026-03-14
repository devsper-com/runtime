---
title: "CLI: memory"
---

# hivemind memory

List and manage memory entries from the default memory store.

## Usage

```bash
hivemind memory [--limit N]
hivemind memory consolidate [--dry-run] [--min-cluster-size 3]
```

## Examples

```bash
hivemind memory
hivemind memory --limit 50
hivemind memory consolidate --dry-run
```

## Behavior

- **List (default):** Lists memory entries from the default memory store.
- **Consolidate:** Clusters similar memories, summarizes clusters, archives originals. Requires `[data]` extra.
