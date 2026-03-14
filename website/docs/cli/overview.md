---
title: CLI Overview
---

# CLI Overview

The Hivemind CLI is invoked as **`hivemind`** (installed with the `hivemind-ai` package). Run `hivemind --help` or `hivemind <command> --help` for usage and examples.

## Commands

| Command | Description |
|---------|-------------|
| `hivemind run` | Run a swarm task |
| `hivemind init` | Initialize a new project |
| `hivemind doctor` | Verify environment and configuration |
| `hivemind tui` | Launch the terminal UI |
| `hivemind workflow` | List, validate, or run workflows |
| `hivemind memory` | List or consolidate memory entries |
| `hivemind credentials` | Manage API keys via OS keychain |
| `hivemind node` | Distributed mode commands |
| `hivemind query` | Query the knowledge graph |
| `hivemind analyze` | Analyze a run or repository |
| `hivemind cache` | Manage the task result cache |
| `hivemind upgrade` | Check for and install updates |

## Global Flags

- `--debug` — Enable debug logging
- `--trace` — Enable trace-level logging
- `--quiet` — Suppress non-essential output
- `--no-color` — Disable colored output
- `--json` — Output as JSON
- `--plain` — Plain text output (no Rich formatting)
