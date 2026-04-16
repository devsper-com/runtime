# Crate Map

The devsper workspace contains 11 crates organized by responsibility. Each crate has a single, clearly bounded role. Dependencies flow in one direction — no circular dependencies.

```
devsper-bin
  ├── devsper-compiler
  │     └── devsper-plugins
  │           └── devsper-core
  ├── devsper-executor
  │     ├── devsper-graph
  │     │     └── devsper-core
  │     ├── devsper-scheduler
  │     │     └── devsper-core
  │     ├── devsper-providers
  │     │     └── devsper-core
  │     └── devsper-plugins
  ├── devsper-bus
  │     └── devsper-core
  ├── devsper-cluster
  │     └── devsper-core
  └── devsper-memory
        └── devsper-core
```

---

## `devsper-core`

**Responsibility:** Zero-dependency shared types and traits. Every other crate depends on this.

**No external deps** beyond `serde`, `serde_json`, `uuid`.

### Types

| Type             | Description                                        |
|------------------|----------------------------------------------------|
| `RunId`          | `Uuid` wrapper for workflow runs.                  |
| `NodeId`         | `Uuid` wrapper for graph nodes.                    |
| `NodeStatus`     | 7-variant enum: Pending/Ready/Running/Completed/Failed/Abandoned/Speculative. |
| `NodeSpec`       | Task definition: name, prompt, model, depends_on, can_mutate. |
| `Node`           | Runtime node: NodeSpec + NodeStatus + result.      |
| `GraphMutation`  | 9-variant enum of graph mutations.                 |
| `GraphSnapshot`  | Serializable full graph state for recovery.        |
| `LlmRequest`     | Model, messages, tools, max_tokens.                |
| `LlmResponse`    | Content, stop_reason, tool_calls.                  |
| `Message`        | Role (System/User/Assistant/Tool) + content.       |
| `ToolDef`        | Tool name, description, param schema.              |
| `ToolCall`       | id, tool name, JSON arguments.                     |
| `ToolResult`     | id, JSON result or error.                          |
| `BusMessage`     | topic, payload, timestamp.                         |
| `RuntimeConfig`  | workers, bus config, evolution settings.           |

### Traits

| Trait         | Methods                                              |
|---------------|------------------------------------------------------|
| `LlmProvider` | `name()`, `supports_model()`, `generate()`           |
| `Bus`         | `publish()`, `subscribe()`, `start()`, `stop()`      |
| `MemoryStore` | `store()`, `retrieve()`, `search()`, `delete()`      |
| `ToolExecutor`| `execute()`, `list_tools()`                          |

---

## `devsper-graph`

**Responsibility:** Self-evolving DAG engine. The performance-critical core.

### Public API

| Item              | Description                                             |
|-------------------|---------------------------------------------------------|
| `GraphActor`      | Owns `petgraph::DiGraph`. Single writer, mpsc-driven.   |
| `GraphHandle`     | Clone-safe async handle for all graph operations.       |
| `MutationValidator` | DFS cycle detection on cloned graph before apply.    |
| `EventLog`        | Append-only `Vec<GraphEvent>`. Auto-snapshot every N.   |
| `GraphSnapshot`   | Full serializable graph state.                          |

`GraphHandle` methods: `mutate()`, `get_ready()`, `claim()`, `complete()`, `fail()`, `snapshot()`, `shutdown()`.

See [Graph Engine](graph-engine.md) for internals.

---

## `devsper-scheduler`

**Responsibility:** Wraps `GraphHandle`, exposes a task-claim API for the executor.

### Public API

| Method                    | Description                                |
|---------------------------|--------------------------------------------|
| `get_ready() → Vec<NodeId>` | Returns nodes ready to execute.          |
| `claim(id)`               | Atomically marks node as Running.          |
| `complete(id, result)`    | Marks node Completed, triggers frontier recompute. |
| `fail(id, error)`         | Marks node Failed, propagates Abandoned.   |

---

## `devsper-executor`

**Responsibility:** Tokio task pool that drives the agent loop.

### Public API

| Item          | Description                                              |
|---------------|----------------------------------------------------------|
| `Executor`    | Semaphore-bounded pool. `run(graph_handle, agent_fn)`.   |
| `AgentOutput` | `{ result: Value, mutations: Vec<GraphMutation> }`       |
| `AgentFn`     | `Arc<dyn Fn(NodeSpec) -> Pin<Box<Future<AgentOutput>>>>` |

The executor polls `get_ready()`, claims nodes, spawns Tokio tasks per agent, applies returned mutations before marking nodes complete. Stall detection after 100 empty polls.

---

## `devsper-bus`

**Responsibility:** Message bus backends.

| Backend       | Type         | Description                                  |
|---------------|--------------|----------------------------------------------|
| `InMemoryBus` | `Bus` impl   | tokio broadcast per topic. Single process.   |
| `RedisBus`    | `Bus` impl   | redis pub/sub + streams. Multi-node.         |
| `KafkaBus`    | `Bus` impl   | Consumer groups. At-least-once.              |

All implement the `Bus` trait from `devsper-core`.

---

## `devsper-providers`

**Responsibility:** LLM HTTP clients and model routing.

| Item                | Description                                     |
|---------------------|-------------------------------------------------|
| `AnthropicProvider` | POST /v1/messages. Streaming support.           |
| `OpenAiProvider`    | POST /v1/chat/completions. Also ZAI via `.zai()` constructor. |
| `OllamaProvider`    | Local Ollama API.                               |
| `MockProvider`      | Deterministic echo. No network.                 |
| `ModelRouter`       | Routes by `supports_model()` prefix.            |

`ModelRouter::default()` registers all built-in providers in priority order.

---

## `devsper-plugins`

**Responsibility:** Lua 5.4 plugin runtime and devsper stdlib.

| Item             | Description                                          |
|------------------|------------------------------------------------------|
| `PluginRuntime`  | Creates Lua VM, injects stdlib, executes plugin source, collects tool registrations. |
| `ToolRegistration` | Tool name + param schema + Lua `run` function ref. |
| `inject_stdlib()`| Injects `devsper` global table into a Lua VM.        |

`inject_stdlib()` provides: `devsper.tool`, `devsper.workflow`, `devsper.exec` (sandboxed), `devsper.http`, `devsper.log`, `devsper.ctx`.

External process mode: tools with `mode = "process"` fork a subprocess and communicate via JSON stdio.

---

## `devsper-compiler`

**Responsibility:** Transforms `.devsper` source into `WorkflowIr`.

| Item                   | Description                                          |
|------------------------|------------------------------------------------------|
| `Compiler`             | `compile_source() → WorkflowIr`, `compile_to_bytecode()`. |
| `WorkflowIr`           | Workflow config + tasks + plugins + inputs.          |
| `WorkflowLoader`       | `load(path)` — handles `.devsper` and `.devsper.bin`.|
| `inject_compiler_stdlib()` | IR-capturing stubs injected at compile time.   |
| `extract_ir()`         | Reads `__workflow__`, `__tasks__`, `__plugins__`, `__inputs__` from Lua globals. |

`compile_to_bytecode()` serializes `WorkflowIr` to JSON. `--embed` mode uses Rust codegen + `cargo build`.

---

## `devsper-cluster`

**Responsibility:** Raft-lite peer mesh for multi-node execution.

| Item          | Description                                            |
|---------------|--------------------------------------------------------|
| `ClusterNode` | Holds NodeRole, term, peer registry, mpsc outbox.      |
| `NodeRole`    | `Coordinator`, `Worker`, `Candidate`.                  |
| `ClusterMessage` | `Hello`, `Heartbeat`, `VoteRequest`, `VoteResponse`, `LeaderElected`, `TaskDispatch`. |

`ClusterNode::start_election()` increments term, broadcasts `VoteRequest`. `become_coordinator()` transitions role and broadcasts `LeaderElected`. Recovery uses `EventLog` snapshot + replay.

---

## `devsper-memory`

**Responsibility:** Agent memory store and retrieval.

| Item                 | Description                                         |
|----------------------|-----------------------------------------------------|
| `LocalMemoryStore`   | In-process HashMap. Namespace-scoped per `{run_id}/{agent_id}`. |
| `EmbeddingIndex`     | TF-IDF cosine similarity for semantic search.       |
| `MemoryRouter`       | Strategy-based retrieval: BM25, Semantic, Hybrid.   |

`MemoryStore` trait methods: `store(namespace, key, value)`, `retrieve(namespace, key)`, `search(namespace, query, strategy, top_k)`, `delete(namespace, key)`.

Hybrid strategy unions BM25 + semantic results and re-ranks by combined score.

---

## `devsper-bin`

**Responsibility:** Thin binary entry point. Wires all crates, handles CLI dispatch.

```rust
#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Run     { spec, .. } => run_command(spec, ...).await,
        Command::Compile { spec, embed } => compile_command(spec, embed).await,
        Command::Peer    { listen, join } => peer_command(listen, join).await,
        Command::Inspect { run_id } => inspect_command(run_id).await,
    }
}
```

`run_command` loads `WorkflowIr`, builds `GraphActor`, converts `TaskIr` → `NodeSpec` with dependency wiring, instantiates `ModelRouter`, wraps provider in `AgentFn`, and calls `Executor::run()`.

The inspect socket (`--inspect-socket`) is a Unix domain socket that streams `GraphEvent` JSON-RPC messages to the TUI.

---

## Dependency matrix

| Crate              | Depends on                                              |
|--------------------|---------------------------------------------------------|
| `devsper-core`     | (none — zero deps except serde/uuid)                    |
| `devsper-graph`    | core, petgraph, tokio                                   |
| `devsper-scheduler`| core, graph                                             |
| `devsper-bus`      | core, tokio, redis (optional), rdkafka (optional)       |
| `devsper-providers`| core, reqwest, tokio                                    |
| `devsper-plugins`  | core, mlua (optional vendored)                          |
| `devsper-compiler` | core, plugins, mlua                                     |
| `devsper-executor` | core, graph, scheduler, providers, plugins              |
| `devsper-cluster`  | core, tokio                                             |
| `devsper-memory`   | core                                                    |
| `devsper-bin`      | all crates, clap, tokio(full)                           |
