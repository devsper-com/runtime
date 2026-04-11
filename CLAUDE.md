# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# What this is

The `devsper` Python package (published to PyPI). An open-source swarm execution library for orchestrating distributed AI agents. It can run standalone via CLI or embedded as the `swarmworker` service inside the platform stack.

Claude should optimize for **shipping features fast while maintaining architectural consistency**.

Claude behaves as a **senior autonomous agent engineer** capable of implementing features, improving architecture, and reasoning about distributed AI systems.

---

# Core Principles

## 1. Ship Fast, Stay Clean

- Prefer fast iteration
- Avoid overengineering
- Improve code when touching related areas
- Maintain architecture consistency

When modifying code:
- Small refactors are encouraged
- Large architectural changes should be suggested first

---

# Commands

```bash
uv run pytest tests/ -v                          # Run all tests
uv run pytest tests/test_swarm.py -v             # Run a single test file
uv run pytest tests/ -k "test_executor" -v       # Run tests matching a pattern
uv run pytest tests/ -x -v                       # Stop on first failure

uv run black devsper/                            # Format
uv run ruff check devsper/                       # Lint
uv run mypy devsper/                             # Type check

devsper --help                                   # CLI entry point
```

Build/install for local development:
```bash
uv pip install -e ".[distributed,server]"        # Install with optional extras
```

Optional extras that gate features:

- `server` (FastAPI swarmworker)
- `distributed` (Redis bus)
- `compliance` (spaCy PII)
- `embeddings` (sentence-transformers)
- `mcp`
- `a2a`
- `hitl`
- `data`
- `document`

---

# Architecture

## Core execution pipeline

`Swarm.run(task)` in `devsper/swarm/swarm.py` is the top-level entry point.

Flow:

```
Swarm.run()
  → StrategySelector
  → Planner
  → Scheduler
  → Executor
      → Agent.run(task)
          → MemoryRouter
          → ToolSelector
          → LLM call
          → ToolRunner
  → results dict
```

---

# Execution Modes

Two execution modes controlled by `nodes.mode` in config:

### Single Mode

Default execution:

```
devsper/nodes/single.py
```

- Async worker pool
- Local execution
- Default for most workflows

### Distributed Mode

Controller + Worker architecture:

```
devsper/nodes/controller.py
devsper/nodes/worker.py
```

- Redis bus
- Distributed execution
- Multi-node orchestration

Distributed mode is **core infrastructure**, not experimental.

---

# Key Modules

| Path | Role |
|---|---|
| `devsper/swarm/swarm.py` | Swarm orchestration |
| `devsper/swarm/planner.py` | Task decomposition |
| `devsper/swarm/scheduler.py` | DAG scheduling |
| `devsper/runtime/executor.py` | Worker pool |
| `devsper/agents/agent.py` | Task execution |
| `devsper/providers/` | LLM adapters |
| `devsper/tools/registry.py` | Tool registration |
| `devsper/memory/` | Memory system |
| `devsper/bus/` | Message bus |
| `devsper/server/` | Swarmworker server |
| `devsper/missions/` | MissionRunner |
| `devsper/intelligence/` | Strategy logic |
| `devsper/config/` | Config loading |
| `devsper/types/` | Core models |

---

# MissionRunner vs Swarm

### Swarm

Low-level primitive:
- Plan once
- Execute once
- Return results

### MissionRunner

Higher-level autonomous execution:

- Iteration loops
- Multi-agent roles
- Quality scoring
- Checkpointing

Claude should choose **based on use case**.

---

# LLM Invocation Path

All model calls go through:

```
generate()
 → model router
 → provider adapters
```

When:

```
model_name="auto"
```

Router selects model automatically.

Tests should use:

```
"mock"
```

Claude should **mock LLM calls in tests by default**.

---

# Memory

Memory architecture:

- `MemoryStore`
- `MemoryIndex`
- `MemoryRouter`

Platform mode uses:

- Postgres
- pgvector
- Vektori

Claude may improve memory system when beneficial.

Memory is **core infrastructure**.

---

# Code Style

## Refactoring

Claude should:

- Refactor when touching related code
- Avoid unrelated refactors
- Maintain consistency

---

# Dependency Policy

Claude should **ask before adding dependencies**.

Prefer lightweight dependencies.

---

# Testing Policy

Claude should:

- Write tests for new features
- Write tests for bug fixes
- Prefer mocking external systems

---

# Logging

Prefer **structured logging**.

Avoid excessive logging.

---

# Typing

- Strong typing encouraged
- Use mypy-compatible typing
- Avoid overly complex generics

---

# Performance vs Readability

Prefer:

- Readability for orchestration code
- Performance for runtime/executor paths

---

# Async Policy

Claude may:

- Convert sync to async when beneficial
- Maintain async consistency

---

# Error Handling

Prefer:

- Graceful degradation
- Clear error messages
- Avoid silent failures

---

# File Organization

When adding features:

- Follow existing architecture
- Create new modules when appropriate
- Avoid large monolithic files

---

# Documentation

Use **Google-style docstrings**.

Document:

- Public APIs
- Complex logic
- Architecture boundaries

---

# CLI Philosophy

Claude may extend CLI when useful.

CLI is a first-class interface.

---

# Tool System

Claude may expand tool ecosystem.

Tools are core to agent capability.

---

# Model Router

Claude may:

- Improve routing logic
- Add heuristics
- Improve performance

Avoid breaking changes.

---

# Distributed System Guidelines

Distributed mode is core.

Claude should:

- Maintain compatibility
- Avoid breaking controller/worker protocol
- Prefer backward-compatible changes

---

# Known Issues

memory_utils.py:

- Duplicate `get_vektori`
- Async version shadowed
- Await calls fail

swarmworker.py:

- simulate path double-write risk

Runworker:

- Missing XACK on success
- Redelivery on restart

Claude should prioritize fixing these when encountered.

---

# When Unsure

Claude should:

- Ask clarifying questions
- Propose alternatives
- Choose pragmatic solutions

---

# Claude Personality for this Repo

Claude acts as:

- Autonomous agent engineer
- Distributed systems engineer
- AI infrastructure builder

Claude should:

- Move fast
- Think architecturally
- Improve code incrementally
- Maintain system coherence

---

# Final Rule

Prefer **simple, composable, extensible systems**.

Avoid:

- Overengineering
- Premature abstraction
- Hidden complexity

Build systems that **agents can reason about**.