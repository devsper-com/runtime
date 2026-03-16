---
sidebar_position: 0
title: Release notes
description: What's new in each release. Mirrored from the GitHub changelog.
---

# Release notes

This page mirrors the [project changelog on GitHub](https://github.com/devsper-com/runtime/blob/main/CHANGELOG.md). Update it when cutting a new release (copy from `CHANGELOG.md` and move **Unreleased** into a new version section).

---

## [Unreleased]

---

## [2.1.5] — 2026-03-11

### Added

- **In-app HITL resolution** — Optional in-process resolver so you can approve/reject HITL requests in the same terminal as `devsper run` (no second terminal). When `hitl.enabled` is true and stdout is a TTY, the CLI prompts with a Rich prompt; resolution is written to ApprovalStore and the run continues or fails based on your choice.
- **HITL in single-node path** — HITL escalation check and resolver/polling now run in the default single-node flow (WorkerNode), not only in the multi-worker Executor path.
- **Better MCP** — `devsper doctor` has a dedicated "MCP Servers" section listing each configured MCP server and tool count (or warnings). Second example MCP server (time server, no API key) in commented block in example devsper.toml.
- Full CLI visual redesign: amber/blue/teal color system across all commands
- Structured logging with tracing-compatible format (matches Rust worker output)
- Live run view: real-time task table, tool activity, cost counter during execution
- Animated planning phase with strategy selection feedback
- Redesigned devsper init: interactive wizard with welcome screen (pyfiglet) and provider/model flow
- Redesigned devsper doctor: themed header and sectioned health check output
- devsperProgress: styled progress bars for long-running operations
- Typed error classes (DevsperError, ProviderConnectionError, ConfigNotFoundError, etc.) with actionable hints and docs links
- Shell completions: bash, zsh, fish (fish hint when shtab used for bash/zsh)
- `--debug`, `--trace`, `--quiet`, `--no-color`, `--json`, `--plain` global flags on all commands
- Auto-plain mode when stdout is not a TTY
- `devsper run --summary` to print only run summary without task results
- New module `devsper/cli/ui/`: theme, components, logging, progress, errors, run_view, onboarding

### Changed

- All CLI output uses themed console (no bare print() in UI code paths)
- Python logging replaced with devsperLogger (tracing-format compatible)
- Error display: no raw tracebacks shown to end users; use print_error/print_unexpected_error
- devsper run shows live view by default when TTY (use `--plain` or pipe for old behavior)
- Docs URLs use https://docs.devsper.com
- **Planner: simple-task fast path** — Short, single-step prompts (e.g. "What is 2+2?") no longer get decomposed into 5 steps; they run as one task and one agent call.
- **Planner: dynamic step count** — Planner prompt asks for "the minimal number of smaller steps needed" instead of a fixed 5; the model can return 1–3 for simple tasks or more for complex ones.

---

## [2.1.0] — 2026-03-11

### Added

- **MetaPlanner** — Decompose mega-tasks into sub-swarms with dependencies, SLAs, and priorities
- **SubSwarmSpec** — Per-swarm priority, SLA, worker count, model override, and `depends_on`
- **SLA monitoring** — Duration/cost/quality breach detection with configurable actions (cancel, escalate, continue)
- **PriorityScheduler** — Priority- and dependency-aware task ordering; `add_task(task, priority)`, `bump_priority(task_id, new_priority)`
- **Human-in-the-Loop (HITL)** — Configurable escalation triggers and approval workflows
- **ApprovalStore** — Persistent pending approvals under `{data_dir}/approvals/` with timeout handling
- **Approval notifications** — Webhook and Slack channels (email logs to stdout without SMTP)
- **CLI** — `devsper meta "<mega-task>"` and `devsper meta plan "<mega-task>"`; `devsper approvals list|show|approve|reject|watch`
- **TASK_REJECTED_BY_HUMAN** event type

---

## [2.0.2] — 2026-03-10

### Fixed

- **Release workflow** — Docs version step skips when version already exists; PyPI publish uses `skip-existing` so re-tags or re-runs don't fail.

---

## [2.0.1] — 2026-03-10

### Added

- **Azure Foundry (v1 API) support** — When `AZURE_OPENAI_ENDPOINT` points to Azure Foundry (URL contains `cognitiveservices.azure.com` or `/openai/v1`), the provider uses the v1 chat-completions API via `ChatOpenAI` with `base_url` instead of the legacy deployment-path API, fixing 404s on Foundry resources.
- **Credentials `set` inline and stdin** — `devsper credentials set <provider> <key> [value]` accepts an optional value; if omitted and stdin is not a TTY, reads value from stdin (e.g. `echo "https://..." | devsper credentials set azure endpoint`).

### Changed

- **Credentials input masking** — Only sensitive keys (`api_key`, `token`) use hidden input; endpoint, deployment, and api_version prompts show typed input.
- **Azure model spec** — Provider strips `provider:` prefix (e.g. `azure:gpt-5-mini` → `gpt-5-mini`) before sending to the API so deployment name is correct.
- **.env.example** — Documents correct Azure Foundry endpoint (`.../openai/v1` for chat completions; avoid `.../openai/responses`).

---

## [2.0.0] — 2026-03-10

### Breaking Changes

- Provider config schema updated: existing provider strings unchanged, new backends require new config sections
- Agent execution now routed through AgentSandbox by default (disable with `sandbox.enabled = false`)
- Memory storage now redacts PII by default if `compliance.pii_redaction = true`

### Added

- Abstract LLM router with Ollama, vLLM, and custom OpenAI-compatible endpoint backends
- Provider fallback chains: automatic failover across backends
- Agent sandboxing: resource quotas, tool category restrictions, per-role sandbox profiles
- Audit logging: append-only JSONL with chain integrity verification
- PII redaction: regex + optional spaCy NER, configurable PII types
- GDPR/CCPA compliance config section
- Decision tree and rationale generation for every agent action
- Simulation mode: dry-run planning without LLM calls or tool execution
- `devsper explain`, `devsper simulate`, `devsper audit` CLI commands
- PROVIDER_FALLBACK event type

### Migration from 1.x

See [Migration to v2](/docs/configuration#migration) (or `docs/migration/v2.md` in the repo).

---

For older releases, see the [full changelog on GitHub](https://github.com/devsper-com/runtime/blob/main/CHANGELOG.md).
