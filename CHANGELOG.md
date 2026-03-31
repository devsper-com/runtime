# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.4.0] — 2026-03-31

### Added

- **Distributed runtime extensions** — Added modular runtime components for distributed orchestration: `AgentPool`, `ModelRouter`, `SpeculativePlanner`, `HITLManager`, `ExecutionGraph` worker assignment tracking, plus distributed wrappers (`distributed/controller.py`, `distributed/worker_runtime.py`).
- **Runtime architecture documentation** — Expanded runtime docs with distributed architecture, worker/controller lifecycle, speculative execution flow, and HITL lifecycle details.
- **Tool execution hardening** — Upgraded runtime tool runner with bounded parallelism, dependency-aware batching, per-call timeout isolation, and cancellation support.

### Changed

- **Executor orchestration** — Runtime executor now supports agent-pool-backed execution, model routing integration, speculative follow-up scheduling hooks, and improved cancellation/backpressure behavior.
- **Prompt/token efficiency** — Tool schema injection in agent prompts was compressed to reduce runtime token overhead in tool-enabled turns.
- **Homepage and release communication** — Updated README homepage with v2.4.0 release CTA and an architecture upgrade blog entry for this release.

## [2.3.0] — 2026-03-30

### Added

- **Autonomous Missions capability layer** — New `devsper.missions` package for long-horizon autonomous execution across research, coding, and experiment workflows.
- **Mission planner and DAG generation** — Added `missions/mission_planner.py` to break goals into mission tasks, assign role agents, and define dependency graphs.
- **Research mission workflow** — Added mission agents (`researcher_agent`, `reviewer_agent`, `writer_agent`, `editor_agent`) and end-to-end flow: research → critique → improve → finalize.
- **Coding mission workflow** — Added mission agents (`architect_agent`, `coder_agent`, `tester_agent`, `debugger_agent`, `docs_agent`) and end-to-end flow: design → code → test → fix → document.
- **Iteration engine** — Added `missions/iteration_loop.py` for quality-threshold-driven iterative execution with critique/improvement cycles.
- **Mission memory** — Added `missions/mission_memory.py` to persist research findings, decisions, and experiment artifacts per mission.
- **Long-running mission support** — Added checkpointing/resume support in `missions/mission_runner.py` plus HITL task-gating callback support.
- **Mission UI** — Added dashboard `MissionView` and TUI mission execution path (`mission:research ...`, `mission:coding ...`, `mission:experiment ...`) to show goal, DAG, and iteration progress.

### Changed

- **SDK surface** — Exported `MissionRunner` from `devsper` package root for straightforward mission execution from Python.
- **Testing** — Added runtime tests for mission DAG planning and checkpoint creation.

## [2.2.0] — 2026-03-28

### Added

- **Supermemory ranking backend** — `[memory] backend = "supermemory"` (default) uses the Rust `supermemory-core` ranker for hybrid lexical (+ optional embedding) memory retrieval, deduplication, and recency-aware context formatting.
- **Platform memory backends** — `[memory] backend` can be `platform` or `hybrid` with `platform_api_url` and `platform_org_slug`; config resolver honors `DEVSPER_PLATFORM_API_URL` and `DEVSPER_PLATFORM_ORG` when set.
- **Remote platform workflows** — `load_workflow("org/pkg@N")` fetches workflow specs from the Devsper Platform API when `DEVSPER_PLATFORM_API_URL`, `DEVSPER_PLATFORM_ORG`, and (when required) `DEVSPER_PLATFORM_TOKEN` are configured.
- **Local worker pool** — `devsper pool` subcommands to run the local worker pool manager (foreground spawner) alongside improved swarm execution when using pool-backed paths.
- **Devsper Cloud CLI** — `devsper cloud login`, `logout`, `run`, `status`, and `logs` for JWT authentication (OS keychain) and runs against the platform API.

### Changed

- **Telemetry** — OpenTelemetry configuration and OTLP export wiring expanded (`otel_endpoint`, `otel_headers`, and related options).
- **Documentation** — README refresh; removed outdated standalone docs where superseded by the current `docs/` tree.

## [2.1.8] — 2026-03-24

### Changed

- **Memory management** — Runtime lifecycle and retention tuned for lower steady-state memory use (agent/worker paths, caches, and long-run cleanup).

## [2.1.7] — 2026-03-18

### Added

- **Multi-format run export** — New `devsper export-runs` command exports run history bundles to Markdown, reStructuredText, LaTeX, BibTeX, HTML, JSON, and DOCX (when `python-docx` is available), with per-run markdown artifacts under `runs/`.
- **Dual PDF pipelines** — Export supports both LaTeX (`pdflatex`) and HTML (`wkhtmltopdf`/`pandoc`) PDF generation, plus manifest reporting for generated outputs and pipeline errors.
- **Branding-aware documents** — Export templates now consume branding tokens and logo assets from `homepage` for consistent "docproc/devsper" presentation.
- **Export docs and tests** — Added `docs/export-runs.md` and automated tests covering format generation and event-path resolution.

### Changed

- **Distributed run stability** — Controller dispatch/claim handling is more robust (slot-aware routing, shorter unclaimed-task requeue path, safer task-completion fallback parsing) to reduce stuck runs.
- **Snapshot restore safety** — Leader restore now avoids rolling back to stale/equivalent snapshots, reducing repeated re-dispatch loops.
- **HITL/MCQ UX** — Clarification prompts now use interactive numeric selection with a custom answer option and explicit "answer received" feedback.
- **Run summary accuracy** — Duration/cost aggregation now uses event-log grounded values for more reliable final summaries.
- **CLI/TUI branding and noise** — Theme/style namespace now prefers `devsper.*` aliases, and TUI logging suppression reduces controller log flooding during active runs.

## [2.1.6] — 2026-03-14

### Added

- **Docs site overhaul** — Completely redesigned landing page at [hivemind.rithul.dev](https://hivemind.rithul.dev) with animated hero, feature grid, code tabs, and registry callout. Restructured sidebar navigation with 7 categories: Getting Started, Core Concepts, Plugins, CLI Reference, Registry, and Self-hosting.
- **Docs hosting on EC2** — Docusaurus static site now served via Caddy alongside the registry at `hivemind.rithul.dev`, with automatic TLS via Let's Encrypt.
- **Unified CI/CD pipeline** — Replaced separate `registry-api.yml` and `registry-web.yml` workflows with a single `registry-deploy.yml` (test, build, push, deploy) using OIDC + EC2 Instance Connect. New `docs-deploy.yml` workflow for automatic docs deployment on push.
- **Registry deployment hardening** — Improved Dockerfiles with multi-stage builds, production-ready Caddy configuration with security headers, and comprehensive deployment documentation.

### Changed

- Docs site uses Geist + JetBrains Mono fonts, amber color system, dark-only mode
- Simplified `docs.yml` workflow to versioning-only (removed GitHub Pages deployment)

## [2.1.5] — 2026-03-11

### Added

- **In-app HITL resolution** — Optional in-process resolver so you can approve/reject HITL requests in the same terminal as `hivemind run` (no second terminal). When `hitl.enabled` is true and stdout is a TTY, the CLI prompts with a Rich prompt; resolution is written to ApprovalStore and the run continues or fails based on your choice.
- **HITL in single-node path** — HITL escalation check and resolver/polling now run in the default single-node flow (WorkerNode), not only in the multi-worker Executor path.
- **Better MCP** — `hivemind doctor` has a dedicated "MCP Servers" section listing each configured MCP server and tool count (or warnings). Second example MCP server (time server, no API key) in commented block in example hivemind.toml.
- Full CLI visual redesign: amber/blue/teal color system across all commands
- Structured logging with tracing-compatible format (matches Rust worker output)
- Live run view: real-time task table, tool activity, cost counter during execution
- Animated planning phase with strategy selection feedback
- Redesigned hivemind init: interactive wizard with welcome screen (pyfiglet) and provider/model flow
- Redesigned hivemind doctor: themed header and sectioned health check output
- HivemindProgress: styled progress bars for long-running operations
- Typed error classes (HivemindError, ProviderConnectionError, ConfigNotFoundError, etc.) with actionable hints and docs links
- Shell completions: bash, zsh, fish (fish hint when shtab used for bash/zsh)
- `--debug`, `--trace`, `--quiet`, `--no-color`, `--json`, `--plain` global flags on all commands
- Auto-plain mode when stdout is not a TTY
- `hivemind run --summary` to print only run summary without task results
- New module `hivemind/cli/ui/`: theme, components, logging, progress, errors, run_view, onboarding

### Changed

- All CLI output uses themed console (no bare print() in UI code paths)
- Python logging replaced with HivemindLogger (tracing-format compatible)
- Error display: no raw tracebacks shown to end users; use print_error/print_unexpected_error
- hivemind run shows live view by default when TTY (use `--plain` or pipe for old behavior)
- Docs URLs use https://hivemind.rithul.dev
- **Planner: simple-task fast path** — Short, single-step prompts (e.g. "What is 2+2?") no longer get decomposed into 5 steps; they run as one task and one agent call.
- **Planner: dynamic step count** — Planner prompt asks for "the minimal number of smaller steps needed" instead of a fixed 5; the model can return 1–3 for simple tasks or more for complex ones.

## [2.1.0] — 2026-03-11

### Added

- **MetaPlanner** — Decompose mega-tasks into sub-swarms with dependencies, SLAs, and priorities
- **SubSwarmSpec** — Per-swarm priority, SLA, worker count, model override, and `depends_on`
- **SLA monitoring** — Duration/cost/quality breach detection with configurable actions (cancel, escalate, continue)
- **PriorityScheduler** — Priority- and dependency-aware task ordering; `add_task(task, priority)`, `bump_priority(task_id, new_priority)`
- **Human-in-the-Loop (HITL)** — Configurable escalation triggers and approval workflows
- **ApprovalStore** — Persistent pending approvals under `{data_dir}/approvals/` with timeout handling
- **Approval notifications** — Webhook and Slack channels (email logs to stdout without SMTP)
- **CLI** — `hivemind meta "<mega-task>"` and `hivemind meta plan "<mega-task>"`; `hivemind approvals list|show|approve|reject|watch`
- **TASK_REJECTED_BY_HUMAN** event type

## [2.0.2] — 2026-03-10

### Fixed

- **Release workflow** — Docs version step skips when version already exists; PyPI publish uses `skip-existing` so re-tags or re-runs don't fail.

## [2.0.1] — 2026-03-10

### Added

- **Azure Foundry (v1 API) support** — When `AZURE_OPENAI_ENDPOINT` points to Azure Foundry (URL contains `cognitiveservices.azure.com` or `/openai/v1`), the provider uses the v1 chat-completions API via `ChatOpenAI` with `base_url` instead of the legacy deployment-path API, fixing 404s on Foundry resources.
- **Credentials `set` inline and stdin** — `hivemind credentials set <provider> <key> [value]` accepts an optional value; if omitted and stdin is not a TTY, reads value from stdin (e.g. `echo "https://..." | hivemind credentials set azure endpoint`).

### Changed

- **Credentials input masking** — Only sensitive keys (`api_key`, `token`) use hidden input; endpoint, deployment, and api_version prompts show typed input.
- **Azure model spec** — Provider strips `provider:` prefix (e.g. `azure:gpt-5-mini` → `gpt-5-mini`) before sending to the API so deployment name is correct.
- **.env.example** — Documents correct Azure Foundry endpoint (`.../openai/v1` for chat completions; avoid `.../openai/responses`).

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
- `hivemind explain`, `hivemind simulate`, `hivemind audit` CLI commands
- PROVIDER_FALLBACK event type

### Migration from 1.x

See docs/migration/v2.md

## [1.10.5] - 2026-03-10

### Added

- MCP (Model Context Protocol) client supporting stdio, HTTP, and SSE transports
- MCPToolAdapter: MCP server tools appear in hivemind tool registry automatically
- MCP server config via `[[mcp.servers]]` in hivemind.toml
- A2A (Agent-to-Agent) client for calling external A2A-compliant agents as tools
- A2AServer: exposes hivemind as an A2A endpoint with AgentCard and task endpoints
- A2AAgentTool: external A2A agent skills registered as local tools
- `hivemind mcp list|test|add` CLI commands
- `hivemind a2a serve|discover|call` CLI commands
- Protocol version constants in `hivemind/protocols/`

### Changed

- Tool category "mcp" and "a2a" added to scoring and selection pipeline

## [1.10.0] - 2026-03-10

### Added

- **Full distribution system (v1.10)** — Production-grade distributed execution across multiple machines or processes: cluster membership, task-aware routing, controller HA via shared state, backpressure-aware dispatch, and partial failure recovery. Single-node mode (default) remains zero-config and behaviorally identical to v1.9.
- **New module `hivemind/cluster/`** — `NodeInfo`, `NodeRole`, `ClusterState`; `ClusterRegistry` (Redis hash: register, heartbeat, deregister, get_workers/get_controllers); `LeaderElector` (Redis SET NX + TTL: campaign, refresh, watch); `StateBackend` ABC with `RedisStateBackend` and `FilesystemStateBackend`; `TaskRouter` (memory/tool/load affinity, version check); `InMemoryRegistry` and `LocalLeaderElector` for single-node.
- **Controller node** — `hivemind/nodes/controller.py`: dispatch loop, checkpoint loop, worker timeout monitor, task claim grant/reject, snapshot on completion; leader election via `elector.watch()`; subscribes to TASK_COMPLETED/FAILED/CLAIMED, NODE_HEARTBEAT/JOINED, SWARM_STATUS_REQUEST.
- **Worker node** — `hivemind/nodes/worker.py`: claim/grant flow for TASK_READY, execute via `agent.run(request)`, heartbeat (active_tasks, cached_tools, completed_task_ids); subscribes to TASK_READY, TASK_CLAIM_GRANTED/REJECTED, SWARM_SNAPSHOT, SWARM_CONTROL (pause/resume/drain).
- **Single-node mode** — `hivemind/nodes/single.py`: `SingleNode` and `create_single_node()` use InMemoryBus, FilesystemStateBackend, in-memory registry/elector; one process runs controller + worker; no Redis. Swarm uses single-node path when `config.nodes.mode == "single"`.
- **RPC layer** — `hivemind/nodes/rpc.py`: FastAPI app with `/health`, `/status`, `/tasks`, `/snapshot` (token-auth), `/control`, `/stream/events`; optional `X-Hivemind-Token` for snapshot/control.
- **New bus topics** — `task.claimed`, `task.claim_granted`, `task.claim_rejected`, `node.became_leader`, `node.lost_leadership`, `swarm.snapshot`, `swarm.status_request`, `swarm.status_response`.
- **Config `[nodes]`** — `mode` (single | distributed), `role` (controller | worker | hybrid), `run_id` (optional, for distributed demo), `rpc_port`, `rpc_token`, `max_workers_per_node`, `node_tags`, `controller_url`, `heartbeat_interval_seconds`, `task_claim_timeout_seconds`. Config loader now merges `[bus]` and `[nodes]` from TOML.
- **CLI: `hivemind node`** — `node start [--role] [--port] [--workers] [--tags]`, `node status [--controller-url]`, `node workers [--controller-url]`, `node drain <node_id>`, `node logs [--follow]`.
- **Doctor** — When `nodes.mode == distributed`: checks Redis reachable, fastapi/uvicorn installed, warns if `rpc_token` unset; when single: "Running in single-node mode — no cluster checks needed."
- **Optional dependency group `[distributed]`** — `redis>=5.0.0`, `fastapi>=0.110.0`, `uvicorn>=0.29.0`, `hiredis>=2.3.0`. Install with `pip install 'hivemind-ai[distributed]'` or `uv sync --extra distributed`.
- **Docker Compose** — `docker-compose.yml` in project root: Redis 7 Alpine on port 6379 with healthcheck and volume.
- **Example: distributed on one machine** — `examples/distributed/`: `controller.toml`, `worker.toml`, `run_controller.py` (plan + start controller + wait for completion), `run_worker.py` (register, run until Ctrl+C), `README.md`, `run_demo.sh`. Start Redis, then workers, then controller; shared `run_id` for cluster.
- **Tool score store** — `get_cached_tool_names()` on `ToolScoreStore` for worker heartbeat and router tool affinity.
- **Tests** — `tests/test_v110.py`: single-node no Redis, single-node results shape, NodeInfo roundtrip, InMemoryRegistry, LocalLeaderElector, FilesystemStateBackend, task routing (low load, version incompatible).
- **Rust-based worker node (hivemind-worker)** — High-performance distributed worker: controller/worker logic in Rust; task claim protocol, leader election, heartbeat, RPC (axum: /health, /status, /tasks, /control, /stream/events); subprocess and PyO3 execution bridges to Python agents; Docker image at ghcr.io (linux/amd64, linux/arm64); SBOM and cosign signing.
- **Bus schema version** — `hivemind/bus/schema_version.py`: `BUS_SCHEMA_VERSION = "1.10"`; Rust worker includes in every BusMessage; Python warns on mismatch.
- **run_agent entry point** — `python -m hivemind.agents.run_agent`: stdin AgentRequest JSON, stdout AgentResponse JSON for Rust subprocess executor.
- **Task round-trip test** — `tests/test_cross_boundary_serialization.py`: 20 Task fixtures across Python/Rust boundary.
- **Credential injection for Rust worker subprocess** — `hivemind.credentials.inject_into_env()`: loads API keys from keychain into `os.environ`; called at startup of `run_agent.py` so the subprocess sees `GITHUB_TOKEN` etc. without exporting env vars.
- **Rust worker env vars** — `HIVEMIND_WORKER_MODEL` (default `mock`; set to `github:gpt-4o` etc. for real LLM), `HIVEMIND_RPC_PORT=0` for any free port (multiple workers on one host), `HIVEMIND_PYTHON_BIN` for venv Python.
- **GitHub provider 429 retry** — Exponential backoff (1s, 2s, 4s, max 32s) for rate-limited requests; up to 3 retries before failing.
- **GitHub provider content extraction** — Handles OpenAI-style `content` as array of `{type: "text", text: "..."}` parts.

### Changed

- Worker node concurrency, heartbeating, and bus I/O can run in Rust (hivemind-worker binary); Python worker remains supported.
- Controller records task in `_pending_claims` **before** publishing TASK_READY so that when the worker replies immediately with TASK_CLAIMED, the controller finds the entry and grants the claim (fixes single-node hang).
- Single-node `run_until_finished()` yields briefly before polling so the event loop runs leader election and dispatch; `LocalLeaderElector.watch()` uses a 0.5s refresh interval for single-node.
- `RedisBus` exposes `redis_client` for cluster registry, election, and state backend.
- **Doctor:** Fixed `UnboundLocalError` for `os` when `[knowledge]` block is present (removed redundant `import os` inside `run_doctor()`).
- **Snapshot restore** — Controller only restores snapshot when task IDs match the current plan; discards stale snapshots from prior runs (e.g. new prompt) so new jobs run correctly.
- **Controller empty result** — When `TASK_COMPLETED` has empty result but `error` set, stores `(Error: ...)` so user sees the failure (e.g. 429, missing token).
- **run_agent** — `agent.run()` is sync; removed incorrect `asyncio.run(agent.run(request))` that raised "coroutine was expected".
- **Example controller** — `task_claim_timeout_seconds = 180` for slow LLM responses; progress message notes LLM latency.
- **Rust worker** — Logs `worker_model` at startup; logs `result_len` and warns on empty result with error.

### Migration

- **Single-node users:** No changes required.
- **Distributed users:** Optionally replace Python worker processes with the `hivemind-worker` Rust binary or Docker image for better performance. See `worker/README.md` and `docs/distributed.md`.

## [1.9.0] - 2026-03-09

### Added

- **Full task and agent serialization (v1.9)** — `Task`: `to_dict`, `from_dict`, `to_json`, `from_json`, `checksum()`; `Event`: JSON-safe payload validation in `__init__` (`EventSerializationError`), `to_dict`/`from_dict`/`to_json`/`from_json`. `AgentRequest` and `AgentResponse` dataclasses with full serialization; `Agent.run(request) -> AgentResponse` (stateless); backward-compat `Agent.run_task(task, ...)`.
- **Real message bus (v1.9)** — New `hivemind/bus/`: `BusMessage`, `get_bus(config)`, `InMemoryBus` (wildcard `task.*`), `RedisBus` (optional `redis` package). Topics: `task.ready`, `task.started`, `task.completed`, `task.failed`, `agent.broadcast`, `swarm.control`, `node.heartbeat`, `node.joined`, `node.left`. Config: `[bus] backend`, `redis_url`. `EventLog.append_event` optionally publishes to bus when `EventLog(bus=...)` is set.
- **Stateless executor (v1.9)** — Executor holds no task state; all state in Scheduler. Receives tasks, builds `AgentRequest`, calls `Agent.run(request)` (via `run_task` for compat), reports via `scheduler.mark_completed(task_id, result)` / `scheduler.mark_failed(task_id, error)`; publishes bus messages for task.started / task.completed / task.failed.
- **Scheduler as single source of truth (v1.9)** — `get_task(task_id)`, `get_all_tasks()`, `get_results()`, `snapshot()` (run_id, tasks, edges, completed_count, failed_count, snapshot_at), `Scheduler.restore(snapshot)`. `mark_completed(task_id, result)`, `mark_failed(task_id, error)`. Task model: `error` field.
- **Checkpointer (v1.9)** — `hivemind/swarm/checkpointer.py`: `SchedulerCheckpointer` writes `scheduler.snapshot()` to `{events_dir}/{run_id}.checkpoint.json` every N task completions; atomic write; `restore_latest(run_id)`, `restore_or_raise(run_id)`. Config: `[swarm] checkpoint_interval`, `checkpoint_enabled`.
- **CLI: `hivemind checkpoint list`** — List checkpoint files with run_id, task counts, timestamp.
- **CLI: `hivemind checkpoint restore <run_id>`** — Restore scheduler from checkpoint (resume execution in 1.10).
- **Health and readiness (v1.9)** — `hivemind/runtime/health.py`: `HealthChecker.check(config) -> HealthReport` (bus_reachable, memory_store_readable, tool_scores_readable, knowledge_graph_loadable, checkpoint_dir_writable). **CLI: `hivemind health`** — Prints ✓/✗ per check; exit 0 if healthy, 1 otherwise (Docker/k8s healthcheck).
- **Exceptions:** `EventSerializationError`, `TaskNotFoundError`, `BusConnectionError`, `CheckpointNotFoundError` in `hivemind/types/exceptions.py`.
- **Tests:** `tests/test_v19.py` (task/event/AgentRequest/AgentResponse roundtrip, event payload JSON-safe, in-memory bus wildcard/order, executor holds no state, scheduler snapshot/restore, checkpointer write/atomic, health all-pass/partial-fail).

### Changed

- Scheduler stores and updates task result/error via `mark_completed(task_id, result)` and `mark_failed(task_id, error)`.
- Swarm sets `scheduler.run_id` from event_log; optionally creates bus and checkpointer from config and passes to Executor.

## [1.8.0] - 2026-03-09

### Added

- **Knowledge-guided planning (v1.8)** — Planner injects relevant prior knowledge from the knowledge graph when confidence > threshold. New `query_for_planning(kg, task_description)` and `PlanningContext` in `hivemind/knowledge/query.py`; planner uses `format_planning_context` in the prompt. Config: `[knowledge] guide_planning`, `min_confidence`. Event: `PLANNER_KG_CONTEXT_INJECTED` (concept_count, finding_count, confidence).
- **Cross-run synthesis (v1.8)** — Answer questions using all memory across runs. New `hivemind/intelligence/synthesis.py` (`CrossRunSynthesizer`). CLI: `hivemind synthesize "<query>"` with `--no-kg`, `--json`, `--since <date>`. Output cites sources as `[run:RUN_ID_SHORT]`.
- **Automatic knowledge extraction (v1.8)** — Post-run heuristic extraction from task results into the knowledge graph. New `hivemind/knowledge/extractor.py` (`KnowledgeExtractor`, `KGNode`, `KGEdge`). Entities: documents (URLs, citations), concepts, datasets, methods. Relationships: uses, extends, outperforms, cites. Config: `[knowledge] auto_extract`, `min_confidence`. Knowledge graph persists to `data_dir/knowledge_graph.json`; `add_or_update_node`, `add_edge`, `save()`, `load()`. Event: `KNOWLEDGE_EXTRACTED` (run_id, nodes_added, edges_added, duration_seconds).
- **Memory consolidation (v1.8)** — Cluster similar memories, summarize clusters, archive originals. New `hivemind/memory/consolidation.py` (`MemoryConsolidator`, `ConsolidationReport`). Schema: `memory` table gains `run_id`, `archived`. `MemoryIndex.query_memory` and `query_across_runs` exclude archived by default; `include_archived` parameter. CLI: `hivemind memory consolidate [--dry-run] [--min-cluster-size 3]`. Event: `MEMORY_CONSOLIDATED`. Requires `scikit-learn` (optional extra `[data]`).
- **Config:** New `[knowledge]` section: `guide_planning`, `min_confidence`, `auto_extract`.
- **Doctor:** Memory stats (active vs archived), warning when >1000 non-archived records; knowledge graph stats (nodes, edges, last updated).
- **Tests:** `tests/test_v18.py` (planning context injected/skipped, synthesizer dedupe/citations, extractor concepts/relationships/confidence, consolidation cluster/dry-run/archived excluded, cross-run query).

### Changed

- Planner accepts optional `knowledge_graph`, `guide_planning`, `min_confidence`; Swarm builds/loads KG when knowledge config is enabled and passes to planner; after run, runs `KnowledgeExtractor.extract_from_run` in background when `auto_extract` is true.
- Memory records store `run_id` (set from event_log when storing swarm memory) and `archived`; `list_memory` supports `include_archived`, `run_id_filter`.
- `hivemind memory` supports subcommands: default list, `memory consolidate`.

## [1.7.0] - 2026-03-09

### Added

- **Critic role (v1.7)** — Lightweight second-pass reviewer that scores task results (completeness, accuracy, actionability) and can request one retry when score &lt; threshold. Runs on the fast model. New module `hivemind/agents/critic.py` (`CriticAgent`, `CritiqueResult`). Config: `[swarm] critic_enabled`, `critic_threshold`, `critic_roles`. Task model: `retry_count`. RunReport: `tasks_critiqued`, `tasks_retried_by_critic`, `avg_critique_score`. Event: `TASK_CRITIQUED`.
- **Agent-to-agent messaging (v1.7)** — Per-run pub/sub message bus so agents can share discoveries. New module `hivemind/agents/message_bus.py` (`SwarmMessageBus`, `AgentMessage`). Agents receive "Shared Discoveries" context and can prefix responses with `BROADCAST: <finding>` to publish. Config: `[swarm] message_bus_enabled`. Event: `AGENT_BROADCAST`.
- **Speculative pre-fetching (v1.7)** — While a task runs, pre-warm memory context and tool selection for likely successor tasks. New module `hivemind/swarm/prefetcher.py` (`TaskPrefetcher`, `PrefetchResult`). Executor triggers prefetch for speculative tasks; agent accepts optional `prefetch_result` and skips memory/tool fetch when present. RunReport: `prefetch_hit_rate`. Config: `[swarm] prefetch_enabled`, `prefetch_max_age_seconds`. Events: `PREFETCH_HIT`, `PREFETCH_MISS`.
- **Structured output self-correction (v1.7)** — Workflow steps with `output_schema` retry with a correction prompt when JSON parsing fails (strip markdown fences, validate required fields and types). New in `hivemind/workflow/runner.py`: `try_parse_structured`, `ParseResult`, `_format_schema`, `_run_step_with_correction`, `WorkflowStepError`. Event: `TASK_STRUCTURED_OUTPUT_CORRECTED`.
- **Config:** `[swarm]` v1.7 keys: `critic_enabled`, `critic_threshold`, `critic_roles`, `message_bus_enabled`, `prefetch_enabled`, `prefetch_max_age_seconds`.
- **Tests:** `tests/test_v17.py` (critic retry/no-retry/max-one, message bus broadcast/exclude-own, prefetch consumed/stale, structured correction strip/error/max-attempts).

### Changed

- Executor accepts optional `critic_agent`, `critic_enabled`, `critic_roles`, `fast_model`, `prefetcher`; runs critic loop after task success for eligible roles and may re-queue one retry.
- Agent accepts optional `message_bus` and `prefetch_result`; injects shared discoveries and uses pre-warmed context when provided.
- Swarm creates one `SwarmMessageBus` per run (when `message_bus_enabled`) and optional `TaskPrefetcher` when speculative execution and `prefetch_enabled`; passes them to executor and agent.
- Workflow steps with `output_schema` use the self-correction loop instead of blind retry; `WorkflowStepError` raised when retries exhausted.

## [1.6.0] - 2026-03-09

### Added

- **Fast Path Execution Engine (v1.6)** — Four independent optimizations for the common case:
  - **Semantic task cache** — Embedding-based similarity lookup instead of exact match only. Configure `[cache]` with `semantic = true`, `similarity_threshold`, `max_age_hours`. New events: `TASK_CACHE_HIT` (task_id, similarity, original_description), `TASK_CACHE_MISS`. Bypass: `HIVEMIND_DISABLE_SEMANTIC_CACHE=1`.
  - **Model complexity routing** — Route tasks to fast / worker / quality models by tier (simple, medium, complex). New `[models]` keys: `fast`, `quality`. New event: `TASK_MODEL_SELECTED` (task_id, tier, model). RunReport: `model_tier_breakdown`, `estimated_cost_without_routing`, `theoretical_sequential_duration`, `actual_duration`, `parallelism_efficiency`.
  - **Streaming DAG unblocking** — Dependents start as soon as each task completes (continuous unblocking) instead of wave-based execution.
  - **Parallel tool execution** — Independent tool calls in a single agent turn run in parallel. Config: `swarm.parallel_tools` (default true). Bypass: `HIVEMIND_DISABLE_PARALLEL_TOOLS=1`.
- **CLI: `hivemind cache tune [--threshold 0.90]`** — Re-evaluate last 50 semantic cache entries at different thresholds for calibration.
- **CLI: `hivemind cache stats`** — Now shows semantic cache status (threshold, entries, hit rate / avg similarity / tokens saved when available).
- **Config:** `[cache]` section (`enabled`, `semantic`, `similarity_threshold`, `max_age_hours`), `[swarm]` `parallel_tools`, `[models]` `fast` and `quality`.
- **Tests:** `tests/test_v16.py` (semantic cache, complexity router, streaming DAG, parallel tools). **Benchmarks:** `tests/benchmarks/test_v16_perf.py` (cache lookup, complexity classification, parallel tools, streaming vs wave).

### Changed

- Executor uses streaming DAG by default; wave-based execution when `streaming_dag=False`.
- Agent accepts `model_override` and `parallel_tools`; tool loop can run multiple tool calls in parallel when `parallel_tools` is true.

## [1.5.0] - 2026-03-09

### Added

- **Run analysis (v1.5)** — Post-run analysis, run history, and interactive TUI controls.
- **New module `hivemind/intelligence/analysis/`** — `run_report.py` (RunReport, TaskSummary, `build_report_from_events`), `cost_estimator.py` (CostEstimator, MODEL_PRICING), `analyzer.py` (LLM plain-English analysis), `formatter.py` (Rich CLI output).
- **CLI: `hivemind analyze <run_id>`** — Build run report from event log; optional `--no-ai` (stats only) and `--json` (raw RunReport). With a path (e.g. `.`) runs repository analysis instead.
- **CLI: `hivemind run-analyze <run_id> [--no-ai] [--json]`** — Explicit run analysis command.
- **CLI: `hivemind runs`** — List run history (Rich table: Run ID, Task, Strategy, Status, Duration, Tasks, Cost, Date). Options: `--limit N`, `--failed`, `--json`. `hivemind runs <run_id>` is shorthand for `hivemind run-analyze <run_id> --no-ai`.
- **Run history** — `hivemind/runtime/run_history.py`: SQLite DB at `~/.config/hivemind/runs.db`; `record_run`, `list_runs`, `get_run`, `delete_run`, `get_stats`. Automatically called at SWARM_FINISHED.
- **TUI: Pause/Resume (keybind `p`)** — SwarmController `pause()`/`resume()` on Swarm; executor checks `pause_event` before picking new tasks; status bar shows "⏸ PAUSED" when paused.
- **TUI: Inject (keybind `i`)** — Overlay "Inject note to swarm"; stored as high-priority MemoryRecord (episodic, tag `user_injection`); MemoryRouter.get_memory_context includes injections; activity feed shows "📌 User injected: {message}".
- **TUI: Task detail (Enter on selected task)** — In Dashboard Tasks view, arrow-key selection and Enter opens detail overlay: full description, result, tools, duration, retry, error.
- **`hivemind doctor`** — Run history checks: DB exists, "Run history: {N} runs, ${cost} total spend"; warns if any run in last 7 days has >50% task failure rate.
- **Tests** — `tests/test_analysis.py`: build_report_from_events, critical path, bottleneck, cost estimate (known/unknown model), run history record/list, runs CLI output, pause stops new tasks, inject in memory context.

### Changed

- Swarm records each run to RunHistory at SWARM_FINISHED.
- Executor accepts optional `pause_event` (threading.Event); when clear, no new tasks start until set.
- MemoryRouter.get_memory_context prepends records with tag `user_injection`.
- MemoryStore.list_memory accepts optional `tag_contains` filter.
- Event type `USER_INJECTION` for inject events in the activity feed.

## [1.4.0] - 2026-03-09

### Added

- **Workflow pipeline engine (v1.4)** — Replaced the sequential step runner with a full pipeline: **typed outputs** between steps, **conditional branching** (`if:`), **explicit dependencies** (`depends_on`), and a **validator** command.
- **New module `hivemind/workflow/`** — `schema.py` (Pydantic DSL: WorkflowDefinition, WorkflowStep, OutputField, StepCondition), `context.py` (WorkflowContext, StepResult, template resolution `{input.x}`, `{steps.id.result}`, `{steps.id.field}`), `conditions.py` (safe `if:` expression evaluation, no eval), `resolver.py` (topological sort, waves, cycle detection), `validator.py` (ValidationReport, reference/DAG/condition checks, dead-output warnings), `runner.py` (WorkflowRunner with parallel waves, retries, output_schema parsing). Loader returns `WorkflowDefinition`; legacy list-of-strings workflows still load and run.
- **CLI:** `hivemind workflow list` — List workflows (name, version, step count, description). `hivemind workflow validate <name>` — Validate and print report (✓/✗/⚠ with Rich). `hivemind workflow run <name> [--input KEY=VALUE ...]` — Run with runtime inputs and summary table. `hivemind workflow <name>` still runs the workflow (backward compatible).
- **Workflow TOML format** — Steps can define `id`, `task`, `depends_on`, `if` (expression), `output_schema` (list of name/type/required), `role`, `model`, `retry`, `timeout_seconds`. Inputs declared in `inputs`; templates use `{input.x}` and `{steps.step_id.result}` or `{steps.step_id.field}` from structured output.
- **Tests** — `tests/test_workflow.py`: sequential/parallel execution, condition skips/blocking, template resolution, output_schema parsing, cycle detection, validator bad reference and dead-output warning, backward compat.

### Changed

- `load_workflow(name)` now returns `WorkflowDefinition | None` (Pydantic model). Legacy workflows (steps as list of strings) are wrapped with auto-generated step ids and sequential dependencies.
- `run_workflow(steps, ...)` (legacy) now uses WorkflowRunner under the hood; return type `dict[str, str]` (step_id → result) unchanged.

## [1.3.0] - 2026-03-09

### Added

- **Tool Reliability Scoring (v1.3)** — Every tool gets a runtime score from real usage; scores feed into tool selection so unreliable tools are demoted over time.
- **`hivemind tools`** — List registered tools with reliability scores (table: Tool Name, Category, Score, Label, Success Rate, Avg Latency, Calls, Last Used). Options: `--category <name>`, `--poor` (score &lt; 0.40). Subcommand `reset <tool_name>` or `reset --all` (with confirmation) wipes score history. Rows colored by label (excellent=green, good=default, degraded=yellow, poor=red); tools with &lt;5 calls show "new".
- **Scoring module** (`hivemind/tools/scoring/`): `ToolScoreStore` (SQLite at `~/.config/hivemind/tool_scores.db`), `ToolScore` dataclass, `record_tool_result`, `get_tool_score`, `get_default_score_store`; `compute_composite_score` and `score_label` in `scorer.py`; `select_tools_scored` (70% similarity + 30% reliability) in `selector.py`; `generate_tools_report` in `report.py`. New tools (&lt;5 calls) get neutral 0.75; `HIVEMIND_DISABLE_TOOL_SCORING=1` bypasses scoring for tests.
- **`hivemind doctor`** — Tool scoring checks: info line "Tool scoring database: {N} records, {M} tools tracked"; warns if &gt;20% of tools with 10+ calls are poor; suggests `hivemind tools reset <name>` for tools with 0% success and ≥10 calls.
- **`hivemind analytics`** — Appends tool reliability report (summary, top 3, bottom 3) when scores exist.
- **Agent** — Uses blended tool selection (similarity × reliability) and passes `task_type` (role or "general") into tool runner for per-context scoring.
- **Tests** — `tests/test_tool_scoring.py`: composite score (new/reliable/dead), score_label, store record/retrieve/prune/reset, selector prefers reliable, similarity dominates, env bypass.

### Changed

- `run_tool(name, args, task_type=None)` now records each run to the scoring store (success/failure, latency, error_type).
- `get_tools_for_task(..., score_store=None)` uses `select_tools_scored` when a score store is provided and scoring is not disabled.

## [1.2.0] - 2026-03-09

### Added

- **`hivemind build`** — Autonomous application builder: generate a working repository from an app description. Orchestrates scaffold → implement → test → debug loop with isolated sandbox and code intelligence (repo index, dependency graph). Use `hivemind build "fastapi todo app"` or `-o ./output` for custom output directory.
- **`hivemind credentials`** — Manage API keys and secrets via the OS keychain (keyring): `set`, `list`, `delete`, `migrate` from `.env`/config, `export` for sourcing. Documented in [CLI](docs/cli.md). Config resolver injects keyring credentials when env vars are not set.
- **`hivemind upgrade`** — Check for updates (PyPI), show changelog between versions, detect installer (pip/uv), and perform upgrade. Supports `--check`, `-y`, `--version`, `--dry-run`. Optional in-session update notice when a new version is available.
- **Credentials module** (`hivemind/credentials/`): `CredentialStore`, keyring-backed storage, migration from config/`.env`.
- **Upgrade module** (`hivemind/upgrade/`): version check with 24h cache, changelog fetch/parse, installer detection, notifier.
- **Dev module** (`hivemind/dev/`): builder, scaffold, sandbox, debugger, repo_index for autonomous app building.
- New dependency: `keyring>=24.0` for secure credential storage.

### Changed

- Config resolution injects credentials from the keyring when the corresponding environment variables are not set, so providers work without storing secrets in config files.
- TUI: dashboard and dev view updates.
- Docs: CLI reference includes `credentials`; configuration and FAQ updated.

## [1.1.1] - 2026-03-09

### Changed

- README logo now uses GitHub raw URL so it displays on PyPI.

## [1.1.0] - 2026-03-09

### Added

- **`hivemind init`** — Set up a new project (creates `hivemind.toml`, example workflow, dataset folder). Documented in [CLI](docs/cli.md).
- **`hivemind doctor`** — Verify environment (API keys, config file, tool registry). Documented in [CLI](docs/cli.md).
- **GitHub Models (Copilot)** — Provider routing with `github:model` (e.g. `github:gpt-4o`, `github:claude-3.5-sonnet`). Set `GITHUB_TOKEN`. Documented in [Providers](docs/providers.md).
- **Automatic model routing** — `planner = "auto"` and `worker = "auto"` in `[models]` for cost/latency/quality-aware selection. Documented in [Providers](docs/providers.md) and [Configuration](docs/configuration.md).

### Changed

- README: PyPI badge fixed (shields.io), badges centered, styling and bloat removed.
- Docs: CLI reference now includes `init` and `doctor`; providers doc covers GitHub Models and auto routing; configuration doc describes `"auto"` for `[models]`.

## [1.0.0] - 2025-03-08

### Added

- **TOML configuration system** (`hivemind/config/`): Pydantic-validated config with `config_loader`, `schema`, `defaults`, `resolver`. Locations: `./hivemind.toml`, `./workflow.hivemind.toml`, `~/.config/hivemind/config.toml`. Priority: env > project > user > defaults. Sections: `[swarm]`, `[models]`, `[memory]`, `[tools]`, `[telemetry]`, `[providers.azure]`.
- **Strategy-based planning** (`hivemind/intelligence/strategies/`): Research, code analysis, data science, document pipeline, and experiment strategies that output DAG tasks. Planner selects strategy automatically (keyword heuristics) and uses strategy DAG when applicable; otherwise falls back to LLM planning.
- **Smart tool selection** (`hivemind/tools/selector.py`): Embed task and tools, select top_k by similarity. Config `[tools] top_k` and `enabled` categories. Optional `category` on Tool base.
- **Map-reduce swarm runtime** (`hivemind/swarm/map_reduce.py`): `swarm.map_reduce(dataset, map_fn, reduce_fn)` with parallel map and single reduce using worker pool.
- **Memory evolution**: `summarizer.py` (extractive/LLM summarization), `namespaces.py` (research_memory, coding_memory, dataset_memory via tags), `scoring.py` (recency, importance, combined ranking).
- **Knowledge graph queries** (`hivemind/knowledge/query.py`): Entity search and relationship traversal. CLI: `hivemind query "diffusion models"`.
- **Plugin ecosystem** (`hivemind/plugins/`): Discover tools via entry_points (`hivemind.plugins`). `plugin_loader.py`, `plugin_registry.py`. Tools package loads plugins after built-in categories.
- **Workflow files**: Load workflows from `workflow.hivemind.toml` (`[workflow] name`, `steps`). CLI: `hivemind workflow <name>`.
- **TUI v2**: Activity Feed and Knowledge Graph viewer panels in dashboard; Memory view supports optional namespace filter.
- **SDK improvements**: `Swarm(config="hivemind.toml")` and `from hivemind import Swarm, get_config`. Config populates worker_count, models, adaptive, use_tools; kwargs override config.
- **Benchmark suite** (`benchmarks/`): bench_research_pipeline, bench_repository_analysis, bench_dataset_analysis (mocked LLM).
- Tests for config loader, strategies, tool selector, map_reduce, memory evolution, plugins, workflow, knowledge query.

### Changed

- Config is now a package `hivemind/config/`; legacy paths (`.hivemind/config.toml`, `[default]`) still supported and mapped into new schema.
- Strategy selector extended with DOCUMENT and EXPERIMENT strategies; planner accepts optional strategy and prompt_suffix.
- Swarm constructor accepts optional `config` (path or object); existing keyword arguments override config.

### Backward compatibility

- v0.1 APIs preserved: `get_config()` returns an object with `worker_model`, `planner_model`, `events_dir`, `data_dir`. `Swarm(worker_count=4, ...)` without config works as before. All existing tests pass.

## [0.1.0] - (existing release)

- Initial release: Planner, Scheduler, Executor, Swarm, Agents, 120+ tools, memory system, knowledge graph, provider routing (OpenAI, Anthropic, Gemini, Azure), EventLog, replay, telemetry, CLI, TUI, examples.
