---
title: Changelog
description: What's new in each release. Mirrored from the GitHub changelog.
---

# Changelog

This page mirrors the [project changelog on GitHub](https://github.com/rithulkamesh/hivemind/blob/main/CHANGELOG.md). Update it when cutting a new release.

---

## [Unreleased]

---

## [2.1.5] — 2026-03-11

### Added

- **In-app HITL resolution** — Optional in-process resolver so you can approve/reject HITL requests in the same terminal as `hivemind run`.
- **HITL in single-node path** — HITL escalation check and resolver/polling now run in the default single-node flow.
- **Better MCP** — `hivemind doctor` has a dedicated "MCP Servers" section.
- Full CLI visual redesign: amber/blue/teal color system across all commands
- Structured logging with tracing-compatible format
- Live run view: real-time task table, tool activity, cost counter during execution
- Animated planning phase with strategy selection feedback
- Redesigned hivemind init: interactive wizard with welcome screen
- Typed error classes with actionable hints and docs links
- Shell completions: bash, zsh, fish
- `--debug`, `--trace`, `--quiet`, `--no-color`, `--json`, `--plain` global flags

### Changed

- All CLI output uses themed console
- Python logging replaced with HivemindLogger
- Error display: no raw tracebacks shown to end users
- **Planner: simple-task fast path** — Short, single-step prompts no longer get decomposed into 5 steps
- **Planner: dynamic step count** — Planner asks for "the minimal number of smaller steps needed"

---

## [2.1.0] — 2026-03-11

### Added

- **MetaPlanner** — Decompose mega-tasks into sub-swarms with dependencies, SLAs, and priorities
- **Human-in-the-Loop (HITL)** — Configurable escalation triggers and approval workflows
- **ApprovalStore** — Persistent pending approvals with timeout handling
- **CLI** — `hivemind meta` and `hivemind approvals` commands

---

## [2.0.0] — 2026-03-10

### Breaking Changes

- Provider config schema updated
- Agent execution now routed through AgentSandbox by default
- Memory storage now redacts PII by default

### Added

- Abstract LLM router with Ollama, vLLM, and custom OpenAI-compatible endpoint backends
- Provider fallback chains: automatic failover across backends
- Agent sandboxing: resource quotas, tool category restrictions
- Audit logging: append-only JSONL with chain integrity verification
- PII redaction and GDPR/CCPA compliance config section
- Simulation mode: dry-run planning without LLM calls
- `hivemind explain`, `hivemind simulate`, `hivemind audit` CLI commands

---

For older releases, see the [full changelog on GitHub](https://github.com/rithulkamesh/hivemind/blob/main/CHANGELOG.md).
