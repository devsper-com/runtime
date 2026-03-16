---
title: CLI Overview
---

# CLI Overview

The devsper CLI is invoked as **`devsper`** (installed with the `devsper` package). Run `devsper --help` or `devsper <command> --help` for usage and examples.

## Commands

| Command | Description |
|---------|-------------|
| `devsper run` | Run a swarm task |
| `devsper init` | Initialize a new project |
| `devsper doctor` | Verify environment and configuration |
| `devsper tui` | Launch the terminal UI |
| `devsper workflow` | List, validate, or run workflows |
| `devsper memory` | List or consolidate memory entries |
| `devsper credentials` | Manage API keys via OS keychain |
| `devsper node` | Distributed mode commands |
| `devsper query` | Query the knowledge graph |
| `devsper analyze` | Analyze a run or repository |
| `devsper cache` | Manage the task result cache |
| `devsper upgrade` | Check for and install updates |

## Global Flags

- `--debug` — Enable debug logging
- `--trace` — Enable trace-level logging
- `--quiet` — Suppress non-essential output
- `--no-color` — Disable colored output
- `--json` — Output as JSON
- `--plain` — Plain text output (no Rich formatting)
