---
title: "CLI: run"
---

# devsper run

Runs the swarm with the given task. The swarm plans subtasks, runs them with agents (with tools and memory if configured), and prints results.

## Usage

```bash
devsper run "task description"
```

## Examples

```bash
devsper run "analyze diffusion models"
devsper run "Summarize swarm intelligence in one paragraph."
devsper run --summary    # print only run summary
```

## Behavior

- Uses config for `worker_model`, `planner_model`, `events_dir`, and memory/data paths.
- Creates an event log in the configured events directory.
- Prints each task ID and its result.
- Shows a live view by default when running in a TTY (use `--plain` for old behavior).
