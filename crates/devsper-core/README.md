# devsper-core

Core types, traits, and shared primitives for the devsper distributed AI runtime.

All other `devsper-*` crates depend on this crate — it defines the contracts that make them composable.

## What's in here

| Item | Description |
|------|-------------|
| `RunId` | Unique identifier for a workflow run |
| `NodeId` | Unique identifier for a task node in a DAG |
| `NodeStatus` | Lifecycle state: `Pending → Ready → Running → Completed / Failed` |
| `GraphSnapshot` | Point-in-time view of all nodes and their statuses |
| `LlmRequest / LlmResponse` | Request/response types for LLM completions |
| `BusMessage` | Envelope for all inter-component events |
| `ToolDef / ToolCall / ToolResult` | Tool use primitives |
| `LlmProvider` | Async trait for LLM backends |
| `Bus` | Async trait for message bus backends |
| `MemoryStore` | Async trait for memory backends |
| `MemoryHit` | Semantic search result |

## Usage

```toml
[dependencies]
devsper-core = "0.1"
```

```rust
use devsper_core::{RunId, NodeId, LlmRequest, LlmProvider};

let run = RunId::new();
let node = NodeId::from_label("summarize");

let req = LlmRequest {
    model: "gpt-4o-mini".into(),
    messages: vec![/* ... */],
    tools: vec![],
    max_tokens: Some(512),
    temperature: None,
    stream: false,
};
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
