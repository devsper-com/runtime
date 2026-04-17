# devsper-memory

Memory system for the devsper runtime. Provides key-value storage, optional embedding-based semantic search, and a routing layer that picks the right retrieval strategy per query.

## Components

| Struct | Role |
|--------|------|
| `LocalMemoryStore` | In-process `HashMap`-backed store; implements `MemoryStore` |
| `MemoryEntry` | Stored value with timestamp and namespace |
| `EmbeddingIndex` | Cosine-similarity index over stored entries (regex-based for zero-dep local use) |
| `MemoryRouter` | Picks `Exact`, `Semantic`, or `Hybrid` retrieval strategy |
| `RetrievalStrategy` | Enum controlling how `MemoryRouter.retrieve()` searches |

## Usage

```toml
[dependencies]
devsper-memory = "0.1"
```

```rust
use devsper_memory::{LocalMemoryStore, MemoryRouter, RetrievalStrategy};
use devsper_core::MemoryStore;
use serde_json::json;

// Basic key-value
let store = LocalMemoryStore::new();
store.store("agent:alice", "last_topic", json!("quantum computing")).await?;
let val = store.retrieve("agent:alice", "last_topic").await?;

// Semantic search
let hits = store.search("agent:alice", "physics research", 3).await?;
for hit in hits {
    println!("{}: {:.2}", hit.key, hit.score);
}

// Router with strategy selection
let router = MemoryRouter::new(store.into());
let results = router.retrieve("agent:alice", "recent papers", 5,
    RetrievalStrategy::Hybrid).await?;
```

## Platform memory (Postgres + pgvector)

When running inside the devsper platform stack, the memory layer is backed by Postgres via Vektori. The `LocalMemoryStore` is used in standalone / test scenarios.

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
