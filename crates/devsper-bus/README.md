# devsper-bus

Message bus backends for the devsper runtime. Implements the `Bus` trait from `devsper-core` with pluggable backends.

## Backends

| Backend | Feature flag | Use case |
|---------|-------------|----------|
| `InMemoryBus` | _(always on)_ | Single-process, testing |
| `RedisBus` | `redis` | Multi-node distributed execution |
| `KafkaBus` | _(stub)_ | High-throughput future use |

## Usage

```toml
[dependencies]
devsper-bus = "0.1"
# For Redis support:
devsper-bus = { version = "0.1", features = ["redis"] }
```

```rust
use devsper_bus::create_bus;
use devsper_core::{Bus, BusMessage};

// "memory" → InMemoryBus, "redis://..." → RedisBus
let bus = create_bus("memory");

bus.subscribe("task.ready", Box::new(|msg| Box::pin(async move {
    println!("task ready: {:?}", msg);
}))).await?;

bus.publish(BusMessage {
    topic: "task.ready".into(),
    payload: serde_json::json!({ "node_id": "fetch" }),
    run_id: "run-123".into(),
}).await?;
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
