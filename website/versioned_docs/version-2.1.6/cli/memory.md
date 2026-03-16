---
title: "CLI: memory"
---

# devsper memory

List and manage memory entries from the default memory store.

## Usage

```bash
devsper memory [--limit N]
devsper memory consolidate [--dry-run] [--min-cluster-size 3]
```

## Examples

```bash
devsper memory
devsper memory --limit 50
devsper memory consolidate --dry-run
```

## Behavior

- **List (default):** Lists memory entries from the default memory store.
- **Consolidate:** Clusters similar memories, summarizes clusters, archives originals. Requires `[data]` extra.
