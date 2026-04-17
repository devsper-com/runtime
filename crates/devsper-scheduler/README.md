# devsper-scheduler

Scheduler facade over `devsper-graph`'s `GraphHandle`. Provides a task-scheduling API oriented around the executor's needs: get ready nodes, claim one, mark done or failed.

The scheduler does **not** own state — all state lives in the `GraphActor`. This makes it safe to create multiple `Scheduler` instances from the same `GraphHandle`.

## Usage

```toml
[dependencies]
devsper-scheduler = "0.1"
```

```rust
use devsper_scheduler::Scheduler;
use devsper_graph::{GraphActor, GraphConfig};

let (_actor, handle) = GraphActor::spawn(GraphConfig::default());
let scheduler = Scheduler::new(handle);

// Poll for work
let ready = scheduler.get_ready().await;

// Race to claim — only one executor wins
if scheduler.claim(ready[0].clone()).await {
    // do work...
    scheduler.complete(ready[0].clone(), serde_json::json!({"ok": true})).await;
}
```

## Distributed claiming

`claim()` is optimistic and race-safe. Multiple worker nodes can call it simultaneously; only the first to succeed executes the node. This is the foundation for distributed execution across a `devsper-cluster`.

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
