# Introduction

## What is Hivemind?

**Hivemind** is a distributed AI swarm runtime for coordinating large numbers of AI agents across complex tasks. It is an open-source framework that lets you run coordinated multi-agent systems using a **swarm execution model**: tasks are decomposed into subtasks, executed by multiple agents in parallel, and coordinated through a scheduler and dependency graph.

## What Problem It Solves

- **Complex task handling** — Single agents often struggle with multi-step, branching work. Hivemind breaks high-level goals into a directed acyclic graph (DAG) of subtasks and runs them with dependency-aware scheduling.
- **Parallelism** — Independent subtasks run concurrently (configurable worker count), so total wall-clock time stays low.
- **Context and memory** — Agents can use a shared memory store (episodic, semantic, research, artifact) and a knowledge graph so later tasks benefit from earlier results.
- **Observability** — A structured event log supports replay, telemetry, and debugging without changing runtime behavior.

## Core Concepts

| Concept | Description |
|--------|-------------|
| **Planner** | Turns one high-level task into an ordered list of subtasks (with optional adaptive expansion). |
| **Scheduler** | Maintains a DAG of tasks and exposes which tasks are ready to run (dependencies satisfied). |
| **Executor** | Runs ready tasks via a worker pool of agents, respecting concurrency limits. |
| **Agent** | Stateless LLM worker that executes a single task (with optional tools and memory context). |
| **Swarm** | Single entrypoint: `Swarm().run("your task")` wires planner → scheduler → executor and returns results. |

## Why Swarm Execution Matters

- **Scalability** — Add more workers to run more subtasks in parallel.
- **Robustness** — Failures or retries can be scoped to individual tasks; the DAG and scheduler keep the rest of the run consistent.
- **Composability** — Tools, memory, and the knowledge graph integrate with the same task/event model, so you can build pipelines (research, codebase analysis, experiments) on top of the same runtime.

## High-Level Overview

1. You give the swarm a **user task** (e.g. “Analyze diffusion models and write a one-page summary”).
2. The **Planner** calls an LLM to break it into **subtasks** (e.g. 5 steps) and emits `task_created` events.
3. The **Scheduler** builds a **DAG** from those subtasks and their dependencies.
4. The **Executor** repeatedly takes **ready** tasks, runs each with an **Agent** (optionally with tools and memory), and marks them completed.
5. Optionally, **adaptive planning** adds new subtasks when a task completes.
6. **Results** are collected; optionally **swarm memory** and **knowledge graph** are updated for future runs.

All of this runs **locally** with minimal setup—no distributed cluster required. Configuration is via environment variables and/or TOML: use `hivemind.toml` or `workflow.hivemind.toml` in the project, or `~/.config/hivemind/config.toml`, or legacy `.hivemind/config.toml`. You can also run predefined **workflows** from `workflow.hivemind.toml` with `hivemind workflow <name>`, and use the **SDK** with `Swarm(config="hivemind.toml")` for a config-driven swarm. From **v1.7**, a **critic** can request one retry for low-scoring results, agents can **broadcast** discoveries to each other, **speculative prefetching** reduces standing-up time, and workflow steps with **structured output** get self-correction when JSON parsing fails.
