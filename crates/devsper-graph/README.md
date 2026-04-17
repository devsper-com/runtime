# devsper-graph

Event-sourced DAG actor for distributed task scheduling in the devsper runtime.

The graph is the source of truth for workflow state. All mutations go through `GraphActor` and are logged as immutable events, enabling full replay and audit.

## Concepts

- **`GraphActor`** — tokio actor owning the `petgraph` DAG; all mutations are serialized through it
- **`GraphHandle`** — cheap clone used by callers to send commands; safe to share across threads
- **`EventLog`** — append-only log of every mutation; enables state reconstruction from scratch
- **`MutationValidator`** — ensures mutations are legal before they're applied (e.g. no cycles, valid transitions)
- **`GraphSnapshot`** — point-in-time view returned to the scheduler/executor

## Usage

```toml
[dependencies]
devsper-graph = "0.1"
```

```rust
use devsper_graph::{GraphConfig, GraphActor, GraphHandle};
use devsper_core::{NodeId, NodeSpec};

let config = GraphConfig::default();
let (actor, handle) = GraphActor::spawn(config);

// Add nodes and edges
handle.add_node(NodeSpec { id: NodeId::from_label("fetch"), .. }).await?;
handle.add_node(NodeSpec { id: NodeId::from_label("summarize"), .. }).await?;
handle.add_edge("fetch", "summarize").await?;

// Get nodes ready to run
let ready: Vec<NodeId> = handle.get_ready().await;

// Claim a node (returns false if another executor won)
let won = handle.claim(ready[0].clone()).await;
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
