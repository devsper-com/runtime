---
title: Quickstart
---

# Quickstart

This guide walks you through running your first hivemind task, using the Python API, and exploring the core CLI commands.

## Run your first task

After [installing hivemind](/docs/getting-started/installation) and configuring at least one API key, run a task directly from the command line:

```bash
hivemind run "Summarize swarm intelligence in one paragraph."
```

hivemind decomposes the task into a DAG of subtasks, executes them across parallel agents, and synthesizes a final result. Output is printed to stdout when complete.

## Using the Python API

You can also drive hivemind programmatically:

```python
from hivemind import Swarm

swarm = Swarm(config="hivemind.toml")
results = swarm.run("Your task here")
print(results)
```

The `Swarm` class accepts a path to a TOML config file or falls back to built-in defaults. The `run` method returns structured results including the final output, execution metadata, and any artifacts produced by agents.

## Creating a config file

Generate a starter `hivemind.toml` in the current directory:

```bash
hivemind init
```

### Basic config example

A minimal configuration that sets the default model and concurrency:

```toml
[swarm]
workers = 4
default_model = "gpt-4o"

[providers.openai]
model = "gpt-4o"

[memory]
enabled = true
backend = "sqlite"
```

All configuration is Pydantic-validated. hivemind will report clear errors if a field has an invalid type or value.

## Running with tools and memory

Enable tools and persistent memory so agents can research, write files, and recall previous results:

```bash
hivemind run "Research recent advances in protein folding and write a summary." \
  --tools research,filesystem \
  --memory
```

Agents select from 120+ built-in tools automatically based on the task. The `--tools` flag restricts the available set when you want tighter control. The `--memory` flag activates the SQLite-backed persistent store so results survive across runs.

## Using the TUI

hivemind includes a terminal user interface for interactive exploration:

```bash
hivemind tui
```

The TUI displays the live DAG, agent activity, streaming output, and memory contents. It is useful for understanding how hivemind decomposes and executes complex tasks.

## Running a workflow

Workflows are multi-step pipelines defined in TOML. Create a workflow file:

```toml
# workflows/research.toml
[workflow]
name = "research_pipeline"

[[workflow.steps]]
name = "gather"
task = "Collect the top 10 papers on {topic}."

[[workflow.steps]]
name = "analyze"
task = "Identify common themes across the collected papers."
depends_on = ["gather"]

[[workflow.steps]]
name = "report"
task = "Write a structured report summarizing findings."
depends_on = ["analyze"]
```

Execute it with:

```bash
hivemind workflow run workflows/research.toml --vars topic="multi-agent systems"
```

Steps run in dependency order, with independent steps executing in parallel.

## Viewing run history

hivemind logs every run. To list past runs:

```bash
hivemind runs
```

To inspect a specific run in detail:

```bash
hivemind runs show <run-id>
```

## Querying results

Search across stored memory and past results:

```bash
hivemind query "What did we learn about protein folding?"
```

This queries the knowledge graph and memory store, returning relevant context from previous runs.

## Next steps

- [Key Concepts](/docs/getting-started/concepts) -- understand the architecture in depth
- [Configuration](/docs/configuration) -- full reference for `hivemind.toml`
- [Tools](/docs/tools) -- browse the 120+ built-in tools
- [Workflows](/docs/concepts/workflows) -- advanced pipeline definitions
