---
title: Introduction
description: What is Hivemind? A distributed AI swarm runtime that coordinates multi-agent systems with a DAG-based swarm execution model, parallelism, and shared memory.
keywords:
  - what is hivemind
  - swarm runtime
  - multi-agent AI
  - DAG
  - planner scheduler executor
slug: /
---

# Introduction

## What is Hivemind?

**Hivemind** is a distributed AI swarm runtime. It coordinates many AI agents on complex tasks. You run multi-agent systems with a **swarm execution model**: the system breaks a task into subtasks, runs them in parallel with multiple agents, and coordinates them through a scheduler and a dependency graph.

## What Problem It Solves

- **Complex task handling** — A single agent often struggles with multi-step, branching work. Hivemind breaks a high-level goal into a DAG of subtasks and runs them with dependency-aware scheduling.
- **Parallelism** — Independent subtasks run at the same time. You set the worker count. Wall-clock time stays low.
- **Context and memory** — Agents share a memory store (episodic, semantic, research, artifact) and a knowledge graph. Later tasks use what earlier tasks learned.
- **Observability** — A structured event log supports replay, telemetry, and debugging. You don't change runtime behavior to inspect it.

## Core Concepts

| Concept | Description |
|--------|-------------|
| **Planner** | Turns one high-level task into an ordered list of subtasks (and can expand the plan as tasks finish). |
| **Scheduler** | Keeps a DAG of tasks and reports which ones are ready to run (dependencies met). |
| **Executor** | Runs ready tasks with a worker pool of agents and enforces concurrency limits. |
| **Agent** | A stateless LLM worker. It runs one task (and can use tools and memory). |
| **Swarm** | The single entrypoint: `Swarm().run("your task")` wires planner, scheduler, and executor and returns results. |

## Why Swarm Execution Matters

- **Scalability** — Add workers to run more subtasks in parallel.
- **Robustness** — A failure or retry affects one task. The DAG and scheduler keep the rest of the run consistent.
- **Composability** — Tools, memory, and the knowledge graph use the same task and event model. You can build pipelines (research, codebase analysis, experiments) on the same runtime.

## High-Level Overview

1. You give the swarm a **user task** (e.g. "Analyze diffusion models and write a one-page summary").
2. The **Planner** uses an LLM to break it into **subtasks** (e.g. five steps) and emits `task_created` events.
3. The **Scheduler** builds a **DAG** from those subtasks and their dependencies.
4. The **Executor** takes **ready** tasks, runs each with an **Agent** (optionally with tools and memory), and marks them completed.
5. Optionally, **adaptive planning** adds new subtasks when a task completes.
6. **Results** are collected. Optionally, swarm memory and the knowledge graph are updated for future runs.

Everything runs **locally** with minimal setup. No distributed cluster. You configure via environment variables and/or TOML: `hivemind.toml` or `workflow.hivemind.toml` in the project, or `~/.config/hivemind/config.toml`, or legacy `.hivemind/config.toml`. Run predefined **workflows** from `workflow.hivemind.toml` with `hivemind workflow <name>`. Use the **SDK** with `Swarm(config="hivemind.toml")` for a config-driven swarm. From **v1.7**, a **critic** can request one retry for low-scoring results, agents can **broadcast** discoveries to each other, **speculative prefetching** reduces standing-up time, and workflow steps with **structured output** get self-correction when JSON parsing fails.
