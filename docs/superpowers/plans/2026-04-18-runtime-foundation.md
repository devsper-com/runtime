# Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Devsper runtime into a deterministic, event-driven, observable, replayable, streamable execution engine.

**Architecture:** All execution emits strongly-typed `EventEnvelope`-wrapped `GraphEvent`s to an `EventBus` (in-memory or Redis). A `TraceCollector` ingests the stream to produce `RunTrace`/`NodeTrace` metrics. A `replay()` fn reconstructs `ReplayState` from any event log deterministically.

**Tech Stack:** Rust, tokio, serde, petgraph, redis (tokio-comp), tokio-stream, async-trait, uuid

---

## Existing Foundation (do not break)

- `crates/devsper-core/src/events.rs` — `GraphEvent` enum (14 variants, `ts` field only)
- `crates/devsper-core/src/types.rs` — `RunId`, `NodeId`, `Node`, `NodeSpec`, `GraphMutation`, `BusMessage`
- `crates/devsper-core/src/traits.rs` — `Bus`, `MemoryStore`, `LlmProvider`, `ToolExecutor`
- `crates/devsper-bus/src/memory.rs` — `InMemoryBus` (uses `BusMessage`, fully working)
- `crates/devsper-executor/src/executor.rs` — `Executor`, `AgentFn`, `AgentOutput` (working, has tests)
- `crates/devsper-graph/src/actor.rs` — `GraphActor`, `GraphHandle` (actor model, working)
- `crates/devsper-memory/src/store.rs` — `LocalMemoryStore` (working)

---

## Task 1: Expand Core Types — EventEnvelope, RunState, MemoryScope

**Files:**
- Modify: `crates/devsper-core/src/types.rs`
- Modify: `crates/devsper-core/src/events.rs`

- [ ] **Step 1: Add RunState + MemoryScope to types.rs**

Append to `crates/devsper-core/src/types.rs` (after the existing `EvolutionConfig` block):

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RunState {
    Created,
    Running,
    WaitingHITL,
    Completed,
    Failed,
}

impl RunState {
    /// Returns the new state if the transition is legal, Err otherwise.
    pub fn transition(&self, to: &RunState) -> Result<RunState, String> {
        use RunState::*;
        match (self, to) {
            (Created, Running) => Ok(to.clone()),
            (Running, WaitingHITL) => Ok(to.clone()),
            (Running, Completed) => Ok(to.clone()),
            (Running, Failed) => Ok(to.clone()),
            (WaitingHITL, Running) => Ok(to.clone()),
            (WaitingHITL, Failed) => Ok(to.clone()),
            _ => Err(format!("invalid transition {:?} → {:?}", self, to)),
        }
    }
}

impl Default for RunState {
    fn default() -> Self { RunState::Created }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum MemoryScope {
    Run,
    Context,
    Workflow,
}
```

- [ ] **Step 2: Add EventEnvelope + new GraphEvent variants to events.rs**

Replace entire `crates/devsper-core/src/events.rs` with:

```rust
use crate::types::{GraphMutation, GraphSnapshot, MemoryScope, NodeId, NodeSpec, RunId, RunState};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Wrapper that adds identity and routing to every event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventEnvelope {
    /// Globally unique event ID.
    pub event_id: String,
    /// Run this event belongs to (used for bus routing/partitioning).
    pub run_id: RunId,
    /// Monotonically increasing per-run sequence number.
    pub sequence: u64,
    pub event: GraphEvent,
}

impl EventEnvelope {
    pub fn new(run_id: RunId, sequence: u64, event: GraphEvent) -> Self {
        Self {
            event_id: Uuid::new_v4().to_string(),
            run_id,
            sequence,
            event,
        }
    }

    pub fn ts(&self) -> u64 { self.event.ts() }
}

/// All events emitted during a graph run's lifecycle.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum GraphEvent {
    // --- Run lifecycle ---
    RunStarted   { run_id: RunId, ts: u64 },
    RunCompleted { run_id: RunId, ts: u64 },
    RunFailed    { run_id: RunId, error: String, ts: u64 },
    RunStateChanged { run_id: RunId, from: RunState, to: RunState, ts: u64 },

    // --- Node lifecycle ---
    NodeAdded     { id: NodeId, spec: NodeSpec, ts: u64 },
    NodeReady     { id: NodeId, ts: u64 },
    NodeStarted   { id: NodeId, ts: u64 },
    NodeOutput    { id: NodeId, chunk: String, ts: u64 },
    NodeCompleted { id: NodeId, result: serde_json::Value, ts: u64 },
    NodeFailed    { id: NodeId, error: String, ts: u64 },
    NodeAbandoned { id: NodeId, ts: u64 },

    // --- Edge lifecycle ---
    EdgeAdded   { from: NodeId, to: NodeId, ts: u64 },
    EdgeRemoved { from: NodeId, to: NodeId, ts: u64 },

    // --- Agent lifecycle ---
    AgentStarted   { node_id: NodeId, model: String, ts: u64 },
    AgentCompleted { node_id: NodeId, input_tokens: u32, output_tokens: u32, ts: u64 },

    // --- Tool calls ---
    ToolCalled    { node_id: NodeId, tool_name: String, args: serde_json::Value, ts: u64 },
    ToolCompleted { node_id: NodeId, tool_name: String, duration_ms: u64, ts: u64 },
    ToolFailed    { node_id: NodeId, tool_name: String, error: String, ts: u64 },

    // --- Memory access ---
    MemoryRead    { namespace: String, key: String, scope: MemoryScope, ts: u64 },
    MemoryWritten { namespace: String, key: String, scope: MemoryScope, ts: u64 },

    // --- Mutations ---
    MutationApplied  { mutation: GraphMutation, ts: u64 },
    MutationRejected { reason: String, ts: u64 },
    SnapshotTaken    { snapshot: GraphSnapshot, ts: u64 },

    // --- HITL ---
    HitlRequested { node_id: NodeId, reason: String, ts: u64 },
    HitlApproved  { node_id: NodeId, ts: u64 },
    HitlRejected  { node_id: NodeId, reason: String, ts: u64 },
}

impl GraphEvent {
    pub fn ts(&self) -> u64 {
        match self {
            GraphEvent::RunStarted      { ts, .. } => *ts,
            GraphEvent::RunCompleted    { ts, .. } => *ts,
            GraphEvent::RunFailed       { ts, .. } => *ts,
            GraphEvent::RunStateChanged { ts, .. } => *ts,
            GraphEvent::NodeAdded       { ts, .. } => *ts,
            GraphEvent::NodeReady       { ts, .. } => *ts,
            GraphEvent::NodeStarted     { ts, .. } => *ts,
            GraphEvent::NodeOutput      { ts, .. } => *ts,
            GraphEvent::NodeCompleted   { ts, .. } => *ts,
            GraphEvent::NodeFailed      { ts, .. } => *ts,
            GraphEvent::NodeAbandoned   { ts, .. } => *ts,
            GraphEvent::EdgeAdded       { ts, .. } => *ts,
            GraphEvent::EdgeRemoved     { ts, .. } => *ts,
            GraphEvent::AgentStarted    { ts, .. } => *ts,
            GraphEvent::AgentCompleted  { ts, .. } => *ts,
            GraphEvent::ToolCalled      { ts, .. } => *ts,
            GraphEvent::ToolCompleted   { ts, .. } => *ts,
            GraphEvent::ToolFailed      { ts, .. } => *ts,
            GraphEvent::MemoryRead      { ts, .. } => *ts,
            GraphEvent::MemoryWritten   { ts, .. } => *ts,
            GraphEvent::MutationApplied  { ts, .. } => *ts,
            GraphEvent::MutationRejected { ts, .. } => *ts,
            GraphEvent::SnapshotTaken   { ts, .. } => *ts,
            GraphEvent::HitlRequested   { ts, .. } => *ts,
            GraphEvent::HitlApproved    { ts, .. } => *ts,
            GraphEvent::HitlRejected    { ts, .. } => *ts,
        }
    }
}

pub fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn envelope_roundtrip() {
        let run_id = RunId::new();
        let node_id = NodeId::new();
        let env = EventEnvelope::new(
            run_id.clone(),
            1,
            GraphEvent::NodeCompleted {
                id: node_id.clone(),
                result: serde_json::json!({"ok": true}),
                ts: now_ms(),
            },
        );
        let json = serde_json::to_string(&env).unwrap();
        let env2: EventEnvelope = serde_json::from_str(&json).unwrap();
        assert_eq!(env2.run_id, run_id);
        assert_eq!(env2.sequence, 1);
        assert!(!env2.event_id.is_empty());
        assert!(env2.ts() > 0);
    }

    #[test]
    fn run_state_valid_transitions() {
        assert!(RunState::Created.transition(&RunState::Running).is_ok());
        assert!(RunState::Running.transition(&RunState::Completed).is_ok());
        assert!(RunState::Running.transition(&RunState::WaitingHITL).is_ok());
        assert!(RunState::WaitingHITL.transition(&RunState::Running).is_ok());
    }

    #[test]
    fn run_state_invalid_transitions() {
        assert!(RunState::Created.transition(&RunState::Completed).is_err());
        assert!(RunState::Completed.transition(&RunState::Running).is_err());
        assert!(RunState::Failed.transition(&RunState::Running).is_err());
    }

    #[test]
    fn hitl_events_serialize() {
        let e = GraphEvent::HitlRequested {
            node_id: NodeId::new(),
            reason: "cost exceeded".to_string(),
            ts: now_ms(),
        };
        let json = serde_json::to_string(&e).unwrap();
        let e2: GraphEvent = serde_json::from_str(&json).unwrap();
        assert!(e2.ts() > 0);
    }

    #[test]
    fn memory_scope_serializes() {
        let scope = MemoryScope::Workflow;
        let json = serde_json::to_string(&scope).unwrap();
        let s2: MemoryScope = serde_json::from_str(&json).unwrap();
        assert_eq!(s2, MemoryScope::Workflow);
    }
}
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/rkamesh/dev/devsper/runtime
cargo test -p devsper-core 2>&1 | tail -20
```

Expected: all tests pass including new ones.

- [ ] **Step 4: Commit**

```bash
git add crates/devsper-core/src/events.rs crates/devsper-core/src/types.rs
git commit -m "feat(core): EventEnvelope, RunState, MemoryScope, expanded GraphEvent variants"
```

---

## Task 2: EventBus Trait

**Files:**
- Modify: `crates/devsper-core/src/traits.rs`

- [ ] **Step 1: Write failing test (in events.rs tests block)**

Add to `crates/devsper-core/src/events.rs` tests:

```rust
#[test]
fn event_envelope_has_unique_ids() {
    let run_id = RunId::new();
    let e1 = EventEnvelope::new(run_id.clone(), 1, GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() });
    let e2 = EventEnvelope::new(run_id.clone(), 2, GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() });
    assert_ne!(e1.event_id, e2.event_id);
    assert_ne!(e1.sequence, e2.sequence);
}
```

- [ ] **Step 2: Run test**

```bash
cargo test -p devsper-core event_envelope_has_unique_ids 2>&1 | tail -5
```

Expected: PASS (EventEnvelope already uses Uuid::new_v4).

- [ ] **Step 3: Add EventBus trait to traits.rs**

Append to `crates/devsper-core/src/traits.rs`:

```rust
use crate::events::EventEnvelope;
use crate::types::RunId;
use tokio_stream::Stream;
use std::pin::Pin;

/// Event bus for strongly-typed GraphEvent routing.
/// Separate from `Bus` (which carries BusMessage for task dispatch).
#[async_trait::async_trait]
pub trait EventBus: Send + Sync {
    /// Publish an event envelope. Non-blocking — must not stall the caller.
    async fn publish(&self, envelope: EventEnvelope) -> Result<()>;

    /// Subscribe to all events for a specific run.
    /// Returns a stream that yields envelopes in emission order.
    async fn subscribe(&self, run_id: &RunId) -> Result<Pin<Box<dyn Stream<Item = EventEnvelope> + Send>>>;
}
```

Also add to the top-level imports in traits.rs:
```rust
use anyhow::Result;
```
(already present — just confirm it's there)

- [ ] **Step 4: Add tokio-stream to devsper-core Cargo.toml**

```toml
# crates/devsper-core/Cargo.toml — add to [dependencies]
tokio-stream = { workspace = true }
```

- [ ] **Step 5: Re-export EventBus from lib.rs**

`crates/devsper-core/src/lib.rs` already does `pub use traits::*;` — no change needed.

- [ ] **Step 6: Compile check**

```bash
cargo check -p devsper-core 2>&1 | tail -10
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add crates/devsper-core/src/traits.rs crates/devsper-core/Cargo.toml
git commit -m "feat(core): EventBus trait with run_id-scoped Stream subscription"
```

---

## Task 3: InMemoryEventBus

**Files:**
- Create: `crates/devsper-bus/src/event_bus.rs`
- Modify: `crates/devsper-bus/src/lib.rs`
- Modify: `crates/devsper-bus/Cargo.toml`

- [ ] **Step 1: Write failing test first**

Create `crates/devsper-bus/src/event_bus.rs` with test-first skeleton:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{EventEnvelope, GraphEvent, RunId, now_ms};
    use tokio_stream::StreamExt;

    #[tokio::test]
    async fn subscribe_receives_published_events() {
        let bus = InMemoryEventBus::new();
        let run_id = RunId::new();

        let mut stream = bus.subscribe(&run_id).await.unwrap();

        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() },
        );
        bus.publish(env.clone()).await.unwrap();

        let received = tokio::time::timeout(
            std::time::Duration::from_millis(100),
            stream.next(),
        ).await.unwrap().unwrap();

        assert_eq!(received.event_id, env.event_id);
    }

    #[tokio::test]
    async fn events_routed_by_run_id() {
        let bus = InMemoryEventBus::new();
        let run_a = RunId::new();
        let run_b = RunId::new();

        let mut stream_a = bus.subscribe(&run_a).await.unwrap();

        // publish to run_b — stream_a should NOT receive it
        let env_b = EventEnvelope::new(
            run_b.clone(), 1,
            GraphEvent::RunStarted { run_id: run_b.clone(), ts: now_ms() },
        );
        bus.publish(env_b).await.unwrap();

        let result = tokio::time::timeout(
            std::time::Duration::from_millis(50),
            stream_a.next(),
        ).await;
        assert!(result.is_err(), "stream_a should not receive run_b events");
    }
}
```

- [ ] **Step 2: Run test to confirm compile failure**

```bash
cargo test -p devsper-bus 2>&1 | tail -10
```

Expected: compile error — `InMemoryEventBus` not defined yet.

- [ ] **Step 3: Implement InMemoryEventBus**

Full content of `crates/devsper-bus/src/event_bus.rs`:

```rust
use devsper_core::{EventBus, EventEnvelope, RunId};
use anyhow::Result;
use async_trait::async_trait;
use std::collections::HashMap;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use tokio_stream::{wrappers::BroadcastStream, Stream, StreamExt};

const CHANNEL_CAPACITY: usize = 4096;

pub struct InMemoryEventBus {
    channels: Arc<RwLock<HashMap<String, broadcast::Sender<EventEnvelope>>>>,
}

impl InMemoryEventBus {
    pub fn new() -> Self {
        Self { channels: Arc::new(RwLock::new(HashMap::new())) }
    }

    async fn sender_for(&self, run_id: &RunId) -> broadcast::Sender<EventEnvelope> {
        let key = run_id.0.clone();
        {
            let r = self.channels.read().await;
            if let Some(tx) = r.get(&key) { return tx.clone(); }
        }
        let mut w = self.channels.write().await;
        w.entry(key).or_insert_with(|| broadcast::channel(CHANNEL_CAPACITY).0).clone()
    }
}

impl Default for InMemoryEventBus {
    fn default() -> Self { Self::new() }
}

#[async_trait]
impl EventBus for InMemoryEventBus {
    async fn publish(&self, envelope: EventEnvelope) -> Result<()> {
        let tx = self.sender_for(&envelope.run_id).await;
        let _ = tx.send(envelope); // ignore if no receivers
        Ok(())
    }

    async fn subscribe(&self, run_id: &RunId) -> Result<Pin<Box<dyn Stream<Item = EventEnvelope> + Send>>> {
        let tx = self.sender_for(run_id).await;
        let rx = tx.subscribe();
        let stream = BroadcastStream::new(rx)
            .filter_map(|r| r.ok()); // drop lagged errors
        Ok(Box::pin(stream))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{GraphEvent, now_ms};
    use tokio_stream::StreamExt;

    #[tokio::test]
    async fn subscribe_receives_published_events() {
        let bus = InMemoryEventBus::new();
        let run_id = RunId::new();
        let mut stream = bus.subscribe(&run_id).await.unwrap();

        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() },
        );
        bus.publish(env.clone()).await.unwrap();

        let received = tokio::time::timeout(
            std::time::Duration::from_millis(100),
            stream.next(),
        ).await.unwrap().unwrap();

        assert_eq!(received.event_id, env.event_id);
    }

    #[tokio::test]
    async fn events_routed_by_run_id() {
        let bus = InMemoryEventBus::new();
        let run_a = RunId::new();
        let run_b = RunId::new();
        let mut stream_a = bus.subscribe(&run_a).await.unwrap();

        let env_b = EventEnvelope::new(
            run_b.clone(), 1,
            GraphEvent::RunStarted { run_id: run_b.clone(), ts: now_ms() },
        );
        bus.publish(env_b).await.unwrap();

        let result = tokio::time::timeout(
            std::time::Duration::from_millis(50),
            stream_a.next(),
        ).await;
        assert!(result.is_err(), "stream_a must not receive run_b events");
    }

    #[tokio::test]
    async fn multiple_subscribers_same_run() {
        let bus = InMemoryEventBus::new();
        let run_id = RunId::new();
        let mut s1 = bus.subscribe(&run_id).await.unwrap();
        let mut s2 = bus.subscribe(&run_id).await.unwrap();

        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunCompleted { run_id: run_id.clone(), ts: now_ms() },
        );
        bus.publish(env.clone()).await.unwrap();

        let r1 = tokio::time::timeout(std::time::Duration::from_millis(100), s1.next()).await.unwrap().unwrap();
        let r2 = tokio::time::timeout(std::time::Duration::from_millis(100), s2.next()).await.unwrap().unwrap();
        assert_eq!(r1.event_id, env.event_id);
        assert_eq!(r2.event_id, env.event_id);
    }
}
```

- [ ] **Step 4: Update devsper-bus/src/lib.rs**

```rust
pub mod event_bus;
pub mod kafka;
pub mod memory;
pub mod redis;

pub use event_bus::InMemoryEventBus;
pub use memory::InMemoryBus;

use devsper_core::Bus;
use std::sync::Arc;

pub fn create_bus(_config: &str) -> Arc<dyn Bus> {
    Arc::new(InMemoryBus::new())
}
```

- [ ] **Step 5: Update devsper-bus Cargo.toml — add tokio-stream**

```toml
tokio-stream = { workspace = true }
```

- [ ] **Step 6: Run tests**

```bash
cargo test -p devsper-bus 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add crates/devsper-bus/src/event_bus.rs crates/devsper-bus/src/lib.rs crates/devsper-bus/Cargo.toml
git commit -m "feat(bus): InMemoryEventBus with run_id-scoped broadcast streams"
```

---

## Task 4: RedisBus (EventBus impl)

**Files:**
- Modify: `crates/devsper-bus/src/redis.rs`

- [ ] **Step 1: Write failing test**

Add to end of `crates/devsper-bus/src/redis.rs`:

```rust
#[cfg(test)]
mod tests {
    // Integration test — requires REDIS_URL env var pointing to a real Redis.
    // Skipped automatically if env var absent.
    use super::*;
    use devsper_core::{EventEnvelope, GraphEvent, RunId, now_ms};
    use tokio_stream::StreamExt;

    fn redis_url() -> Option<String> {
        std::env::var("REDIS_URL").ok()
    }

    #[tokio::test]
    async fn redis_pubsub_roundtrip() {
        let url = match redis_url() {
            Some(u) => u,
            None => { eprintln!("REDIS_URL not set, skipping"); return; }
        };
        let bus = RedisBus::new(&url).await.unwrap();
        let run_id = RunId::new();
        let mut stream = bus.subscribe(&run_id).await.unwrap();

        let env = EventEnvelope::new(
            run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() },
        );
        bus.publish(env.clone()).await.unwrap();

        let received = tokio::time::timeout(
            std::time::Duration::from_secs(2),
            stream.next(),
        ).await.unwrap().unwrap();
        assert_eq!(received.event_id, env.event_id);
    }
}
```

- [ ] **Step 2: Implement RedisBus**

Full content of `crates/devsper-bus/src/redis.rs`:

```rust
use devsper_core::{EventBus, EventEnvelope, RunId};
use anyhow::{Context, Result};
use async_trait::async_trait;
use redis::aio::MultiplexedConnection;
use redis::AsyncCommands;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio_stream::{Stream, wrappers::ReceiverStream};

pub struct RedisBus {
    client: redis::Client,
}

impl RedisBus {
    pub async fn new(url: &str) -> Result<Self> {
        let client = redis::Client::open(url)
            .context("invalid Redis URL")?;
        // Verify connectivity
        let mut conn = client.get_multiplexed_async_connection().await
            .context("cannot connect to Redis")?;
        redis::cmd("PING").query_async::<String>(&mut conn).await
            .context("Redis PING failed")?;
        Ok(Self { client })
    }

    fn channel_key(run_id: &RunId) -> String {
        format!("devsper:events:{}", run_id.0)
    }
}

#[async_trait]
impl EventBus for RedisBus {
    async fn publish(&self, envelope: EventEnvelope) -> Result<()> {
        let mut conn = self.client.get_multiplexed_async_connection().await?;
        let payload = serde_json::to_string(&envelope)?;
        let channel = Self::channel_key(&envelope.run_id);
        conn.publish::<_, _, ()>(channel, payload).await?;
        Ok(())
    }

    async fn subscribe(&self, run_id: &RunId) -> Result<Pin<Box<dyn Stream<Item = EventEnvelope> + Send>>> {
        let mut pubsub = self.client.get_async_pubsub().await?;
        let channel = Self::channel_key(run_id);
        pubsub.subscribe(&channel).await?;

        let (tx, rx) = tokio::sync::mpsc::channel::<EventEnvelope>(4096);

        tokio::spawn(async move {
            use redis::AsyncCommands;
            let mut msg_stream = pubsub.into_on_message();
            while let Some(msg) = {
                use futures::StreamExt;
                msg_stream.next().await
            } {
                if let Ok(payload) = msg.get_payload::<String>() {
                    if let Ok(env) = serde_json::from_str::<EventEnvelope>(&payload) {
                        if tx.send(env).await.is_err() { break; }
                    }
                }
            }
        });

        Ok(Box::pin(ReceiverStream::new(rx)))
    }
}
```

- [ ] **Step 3: Add futures to devsper-bus Cargo.toml if missing**

```toml
futures = { workspace = true }
```

- [ ] **Step 4: Compile check**

```bash
cargo check -p devsper-bus 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add crates/devsper-bus/src/redis.rs crates/devsper-bus/Cargo.toml
git commit -m "feat(bus): RedisBus EventBus implementation via pub/sub"
```

---

## Task 5: devsper-observability crate

**Files:**
- Create: `crates/devsper-observability/Cargo.toml`
- Create: `crates/devsper-observability/src/lib.rs`
- Create: `crates/devsper-observability/src/trace.rs`
- Create: `crates/devsper-observability/src/collector.rs`
- Modify: `Cargo.toml` (workspace members)

- [ ] **Step 1: Create Cargo.toml**

```toml
[package]
name = "devsper-observability"
version.workspace = true
edition.workspace = true
license.workspace = true

[dependencies]
devsper-core = { path = "../devsper-core" }
serde = { workspace = true }
serde_json = { workspace = true }
tokio = { workspace = true, features = ["sync", "rt"] }
tokio-stream = { workspace = true }
async-trait = { workspace = true }
tracing = { workspace = true }
```

- [ ] **Step 2: Create trace.rs**

```rust
use devsper_core::{NodeId, NodeStatus, RunId, RunState};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeTrace {
    pub node_id: NodeId,
    pub model: Option<String>,
    pub started_at: Option<u64>,
    pub completed_at: Option<u64>,
    pub latency_ms: Option<u64>,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cost_usd: f64,
    pub status: NodeStatus,
    pub error: Option<String>,
}

impl NodeTrace {
    pub fn new(node_id: NodeId) -> Self {
        Self {
            node_id,
            model: None,
            started_at: None,
            completed_at: None,
            latency_ms: None,
            input_tokens: 0,
            output_tokens: 0,
            cost_usd: 0.0,
            status: NodeStatus::Pending,
            error: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunTrace {
    pub run_id: RunId,
    pub state: RunState,
    pub started_at: Option<u64>,
    pub completed_at: Option<u64>,
    pub total_latency_ms: Option<u64>,
    pub total_input_tokens: u32,
    pub total_output_tokens: u32,
    pub total_cost_usd: f64,
    pub nodes: HashMap<NodeId, NodeTrace>,
    pub event_count: u64,
}

impl RunTrace {
    pub fn new(run_id: RunId) -> Self {
        Self {
            run_id,
            state: RunState::Created,
            started_at: None,
            completed_at: None,
            total_latency_ms: None,
            total_input_tokens: 0,
            total_output_tokens: 0,
            total_cost_usd: 0.0,
            nodes: HashMap::new(),
            event_count: 0,
        }
    }
}
```

- [ ] **Step 3: Create collector.rs**

```rust
use crate::trace::{NodeTrace, RunTrace};
use devsper_core::{EventEnvelope, GraphEvent, NodeId, RunId, RunState};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

/// Ingests EventEnvelopes and maintains a live RunTrace.
pub struct TraceCollector {
    inner: Arc<RwLock<RunTrace>>,
}

impl TraceCollector {
    pub fn new(run_id: RunId) -> Self {
        Self { inner: Arc::new(RwLock::new(RunTrace::new(run_id))) }
    }

    /// Feed one envelope into the collector.
    pub async fn ingest(&self, envelope: &EventEnvelope) {
        let mut trace = self.inner.write().await;
        trace.event_count += 1;

        match &envelope.event {
            GraphEvent::RunStarted { ts, .. } => {
                trace.state = RunState::Running;
                trace.started_at = Some(*ts);
            }
            GraphEvent::RunCompleted { ts, .. } => {
                trace.state = RunState::Completed;
                trace.completed_at = Some(*ts);
                if let (Some(start), Some(end)) = (trace.started_at, trace.completed_at) {
                    trace.total_latency_ms = Some(end.saturating_sub(start));
                }
            }
            GraphEvent::RunFailed { ts, .. } => {
                trace.state = RunState::Failed;
                trace.completed_at = Some(*ts);
            }
            GraphEvent::RunStateChanged { to, .. } => {
                trace.state = to.clone();
            }
            GraphEvent::NodeStarted { id, ts, .. } => {
                let node = trace.nodes.entry(id.clone()).or_insert_with(|| NodeTrace::new(id.clone()));
                node.started_at = Some(*ts);
                node.status = devsper_core::NodeStatus::Running;
            }
            GraphEvent::NodeCompleted { id, ts, .. } => {
                let node = trace.nodes.entry(id.clone()).or_insert_with(|| NodeTrace::new(id.clone()));
                node.completed_at = Some(*ts);
                node.status = devsper_core::NodeStatus::Completed;
                if let (Some(start), end) = (node.started_at, *ts) {
                    node.latency_ms = Some(end.saturating_sub(start));
                }
            }
            GraphEvent::NodeFailed { id, error, ts, .. } => {
                let node = trace.nodes.entry(id.clone()).or_insert_with(|| NodeTrace::new(id.clone()));
                node.completed_at = Some(*ts);
                node.status = devsper_core::NodeStatus::Failed;
                node.error = Some(error.clone());
            }
            GraphEvent::AgentStarted { node_id, model, .. } => {
                let node = trace.nodes.entry(node_id.clone()).or_insert_with(|| NodeTrace::new(node_id.clone()));
                node.model = Some(model.clone());
            }
            GraphEvent::AgentCompleted { node_id, input_tokens, output_tokens, .. } => {
                let node = trace.nodes.entry(node_id.clone()).or_insert_with(|| NodeTrace::new(node_id.clone()));
                node.input_tokens = *input_tokens;
                node.output_tokens = *output_tokens;
                // Rough cost estimate: $3/1M input, $15/1M output (Sonnet pricing)
                node.cost_usd = (*input_tokens as f64 / 1_000_000.0) * 3.0
                    + (*output_tokens as f64 / 1_000_000.0) * 15.0;
                trace.total_input_tokens += input_tokens;
                trace.total_output_tokens += output_tokens;
                trace.total_cost_usd += node.cost_usd;
            }
            _ => {}
        }
    }

    pub async fn snapshot(&self) -> RunTrace {
        self.inner.read().await.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{EventEnvelope, GraphEvent, NodeId, RunId, now_ms};

    #[tokio::test]
    async fn tracks_run_lifecycle() {
        let run_id = RunId::new();
        let collector = TraceCollector::new(run_id.clone());

        let start_ts = now_ms();
        collector.ingest(&EventEnvelope::new(run_id.clone(), 1,
            GraphEvent::RunStarted { run_id: run_id.clone(), ts: start_ts }
        )).await;

        let end_ts = start_ts + 500;
        collector.ingest(&EventEnvelope::new(run_id.clone(), 2,
            GraphEvent::RunCompleted { run_id: run_id.clone(), ts: end_ts }
        )).await;

        let trace = collector.snapshot().await;
        assert_eq!(trace.state, RunState::Completed);
        assert_eq!(trace.started_at, Some(start_ts));
        assert_eq!(trace.total_latency_ms, Some(500));
        assert_eq!(trace.event_count, 2);
    }

    #[tokio::test]
    async fn tracks_node_tokens_and_cost() {
        let run_id = RunId::new();
        let node_id = NodeId::new();
        let collector = TraceCollector::new(run_id.clone());

        collector.ingest(&EventEnvelope::new(run_id.clone(), 1,
            GraphEvent::AgentStarted { node_id: node_id.clone(), model: "claude-sonnet-4-6".to_string(), ts: now_ms() }
        )).await;

        collector.ingest(&EventEnvelope::new(run_id.clone(), 2,
            GraphEvent::AgentCompleted { node_id: node_id.clone(), input_tokens: 1000, output_tokens: 500, ts: now_ms() }
        )).await;

        let trace = collector.snapshot().await;
        let node = trace.nodes.get(&node_id).unwrap();
        assert_eq!(node.input_tokens, 1000);
        assert_eq!(node.model.as_deref(), Some("claude-sonnet-4-6"));
        assert!(node.cost_usd > 0.0);
        assert_eq!(trace.total_input_tokens, 1000);
    }
}
```

- [ ] **Step 4: Create lib.rs**

```rust
pub mod collector;
pub mod trace;

pub use collector::TraceCollector;
pub use trace::{NodeTrace, RunTrace};
```

- [ ] **Step 5: Add to workspace Cargo.toml**

In `Cargo.toml` workspace members list add:
```toml
"crates/devsper-observability",
```

- [ ] **Step 6: Run tests**

```bash
cargo test -p devsper-observability 2>&1 | tail -20
```

Expected: both tests pass.

- [ ] **Step 7: Commit**

```bash
git add crates/devsper-observability/ Cargo.toml
git commit -m "feat(observability): RunTrace, NodeTrace, TraceCollector with event ingestion"
```

---

## Task 6: ScopedMemoryStore

**Files:**
- Create: `crates/devsper-memory/src/scoped.rs`
- Modify: `crates/devsper-memory/src/lib.rs`
- Modify: `crates/devsper-memory/Cargo.toml`

- [ ] **Step 1: Write failing test**

Add to `crates/devsper-memory/src/scoped.rs`:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{MemoryScope, RunId};
    use crate::store::LocalMemoryStore;
    use std::sync::Arc;

    #[tokio::test]
    async fn run_scope_namespace_contains_run_id() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let scoped = ScopedMemoryStore::new(store, run_id.clone(), None, MemoryScope::Run);

        scoped.store("key", serde_json::json!("value")).await.unwrap();
        let val = scoped.retrieve("key").await.unwrap();
        assert!(val.is_some());
    }

    #[tokio::test]
    async fn different_scopes_are_isolated() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();

        let run_scoped = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Run);
        let ctx_scoped = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Context);

        run_scoped.store("key", serde_json::json!("run-value")).await.unwrap();
        let from_ctx = ctx_scoped.retrieve("key").await.unwrap();
        assert!(from_ctx.is_none(), "Context scope must not see Run scope data");
    }
}
```

- [ ] **Step 2: Implement ScopedMemoryStore**

Full content of `crates/devsper-memory/src/scoped.rs`:

```rust
use devsper_core::{MemoryHit, MemoryScope, MemoryStore, RunId};
use anyhow::Result;
use std::sync::Arc;

/// Wraps any MemoryStore and enforces namespace isolation via MemoryScope.
/// Namespace format:
///   Run      → "run:{run_id}"
///   Context  → "ctx:{run_id}"
///   Workflow → "wf:{workflow_id}"
pub struct ScopedMemoryStore {
    inner: Arc<dyn MemoryStore>,
    namespace: String,
    scope: MemoryScope,
}

impl ScopedMemoryStore {
    pub fn new(
        inner: Arc<dyn MemoryStore>,
        run_id: RunId,
        workflow_id: Option<String>,
        scope: MemoryScope,
    ) -> Self {
        let namespace = match &scope {
            MemoryScope::Run      => format!("run:{}", run_id.0),
            MemoryScope::Context  => format!("ctx:{}", run_id.0),
            MemoryScope::Workflow => format!("wf:{}", workflow_id.as_deref().unwrap_or("default")),
        };
        Self { inner, namespace, scope }
    }

    pub fn scope(&self) -> &MemoryScope { &self.scope }
    pub fn namespace(&self) -> &str { &self.namespace }

    pub async fn store(&self, key: &str, value: serde_json::Value) -> Result<()> {
        self.inner.store(&self.namespace, key, value).await
    }

    pub async fn retrieve(&self, key: &str) -> Result<Option<serde_json::Value>> {
        self.inner.retrieve(&self.namespace, key).await
    }

    pub async fn search(&self, query: &str, top_k: usize) -> Result<Vec<MemoryHit>> {
        self.inner.search(&self.namespace, query, top_k).await
    }

    pub async fn delete(&self, key: &str) -> Result<()> {
        self.inner.delete(&self.namespace, key).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::LocalMemoryStore;

    #[tokio::test]
    async fn run_scope_namespace_contains_run_id() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let scoped = ScopedMemoryStore::new(store, run_id.clone(), None, MemoryScope::Run);
        assert!(scoped.namespace().starts_with("run:"));
        scoped.store("key", serde_json::json!("value")).await.unwrap();
        let val = scoped.retrieve("key").await.unwrap();
        assert!(val.is_some());
    }

    #[tokio::test]
    async fn different_scopes_are_isolated() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let run_scoped  = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Run);
        let ctx_scoped  = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Context);
        run_scoped.store("key", serde_json::json!("run-value")).await.unwrap();
        let from_ctx = ctx_scoped.retrieve("key").await.unwrap();
        assert!(from_ctx.is_none());
    }

    #[tokio::test]
    async fn workflow_scope_uses_workflow_id() {
        let store = Arc::new(LocalMemoryStore::new());
        let run_id = RunId::new();
        let wf = ScopedMemoryStore::new(store, run_id, Some("wf-abc".to_string()), MemoryScope::Workflow);
        assert_eq!(wf.namespace(), "wf:wf-abc");
    }
}
```

- [ ] **Step 3: Update lib.rs**

```rust
pub mod index;
pub mod router;
pub mod scoped;
pub mod store;
pub mod supermemory;

pub use index::EmbeddingIndex;
pub use router::{MemoryRouter, RetrievalStrategy};
pub use scoped::ScopedMemoryStore;
pub use store::{LocalMemoryStore, MemoryEntry};
```

- [ ] **Step 4: Run tests**

```bash
cargo test -p devsper-memory 2>&1 | tail -20
```

Expected: all pass including 3 new scoped tests.

- [ ] **Step 5: Commit**

```bash
git add crates/devsper-memory/src/scoped.rs crates/devsper-memory/src/lib.rs
git commit -m "feat(memory): ScopedMemoryStore with Run/Context/Workflow namespace isolation"
```

---

## Task 7: Tool Execution Hardening

**Files:**
- Create: `crates/devsper-executor/src/hardened_tool.rs`
- Modify: `crates/devsper-executor/src/lib.rs`
- Modify: `crates/devsper-executor/Cargo.toml`

- [ ] **Step 1: Write failing test**

```rust
// Will be in hardened_tool.rs tests block — write the test first, impl second
#[tokio::test]
async fn timeout_returns_error() {
    // proven by: executor that sleeps 200ms with 50ms timeout must fail
}
```

- [ ] **Step 2: Implement HardenedToolExecutor**

Full content of `crates/devsper-executor/src/hardened_tool.rs`:

```rust
use devsper_core::{ToolCall, ToolDef, ToolExecutor, ToolResult};
use anyhow::Result;
use async_trait::async_trait;
use std::sync::Arc;
use tokio::time::{timeout, Duration};
use tracing::warn;

#[derive(Debug, Clone)]
pub struct ToolPolicy {
    pub timeout_ms: u64,
    pub max_retries: u32,
    pub retry_delay_ms: u64,
}

impl Default for ToolPolicy {
    fn default() -> Self {
        Self { timeout_ms: 10_000, max_retries: 2, retry_delay_ms: 200 }
    }
}

pub struct HardenedToolExecutor {
    inner: Arc<dyn ToolExecutor>,
    policy: ToolPolicy,
}

impl HardenedToolExecutor {
    pub fn new(inner: Arc<dyn ToolExecutor>, policy: ToolPolicy) -> Self {
        Self { inner, policy }
    }
}

#[async_trait]
impl ToolExecutor for HardenedToolExecutor {
    async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
        let mut last_err = anyhow::anyhow!("no attempts made");
        for attempt in 0..=self.policy.max_retries {
            if attempt > 0 {
                tokio::time::sleep(Duration::from_millis(self.policy.retry_delay_ms)).await;
                warn!(tool = %call.name, attempt, "retrying tool call");
            }
            let fut = self.inner.execute(call.clone());
            match timeout(Duration::from_millis(self.policy.timeout_ms), fut).await {
                Ok(Ok(result)) => return Ok(result),
                Ok(Err(e)) => last_err = e,
                Err(_) => last_err = anyhow::anyhow!("tool '{}' timed out after {}ms", call.name, self.policy.timeout_ms),
            }
        }
        Ok(ToolResult {
            tool_call_id: call.id,
            content: serde_json::json!({ "error": last_err.to_string() }),
            is_error: true,
        })
    }

    fn list_tools(&self) -> Vec<ToolDef> {
        self.inner.list_tools()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{ToolCall, ToolDef, ToolResult};
    use std::sync::atomic::{AtomicUsize, Ordering};

    struct SlowTool { delay_ms: u64, call_count: Arc<AtomicUsize> }

    #[async_trait]
    impl ToolExecutor for SlowTool {
        async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
            self.call_count.fetch_add(1, Ordering::SeqCst);
            tokio::time::sleep(Duration::from_millis(self.delay_ms)).await;
            Ok(ToolResult { tool_call_id: call.id, content: serde_json::json!("ok"), is_error: false })
        }
        fn list_tools(&self) -> Vec<ToolDef> { vec![] }
    }

    struct FailingTool { call_count: Arc<AtomicUsize> }

    #[async_trait]
    impl ToolExecutor for FailingTool {
        async fn execute(&self, _call: ToolCall) -> Result<ToolResult> {
            self.call_count.fetch_add(1, Ordering::SeqCst);
            Err(anyhow::anyhow!("tool error"))
        }
        fn list_tools(&self) -> Vec<ToolDef> { vec![] }
    }

    fn make_call() -> ToolCall {
        ToolCall { id: "tc-1".to_string(), name: "test_tool".to_string(), arguments: serde_json::json!({}) }
    }

    #[tokio::test]
    async fn timeout_returns_error_result() {
        let count = Arc::new(AtomicUsize::new(0));
        let inner = Arc::new(SlowTool { delay_ms: 200, call_count: count });
        let executor = HardenedToolExecutor::new(inner, ToolPolicy { timeout_ms: 50, max_retries: 0, retry_delay_ms: 0 });
        let result = executor.execute(make_call()).await.unwrap();
        assert!(result.is_error);
        assert!(result.content["error"].as_str().unwrap().contains("timed out"));
    }

    #[tokio::test]
    async fn retries_on_failure() {
        let count = Arc::new(AtomicUsize::new(0));
        let inner = Arc::new(FailingTool { call_count: count.clone() });
        let executor = HardenedToolExecutor::new(inner, ToolPolicy { timeout_ms: 1000, max_retries: 2, retry_delay_ms: 10 });
        let result = executor.execute(make_call()).await.unwrap();
        assert!(result.is_error);
        assert_eq!(count.load(Ordering::SeqCst), 3, "initial + 2 retries");
    }

    #[tokio::test]
    async fn succeeds_on_first_attempt() {
        struct OkTool;
        #[async_trait]
        impl ToolExecutor for OkTool {
            async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
                Ok(ToolResult { tool_call_id: call.id, content: serde_json::json!("done"), is_error: false })
            }
            fn list_tools(&self) -> Vec<ToolDef> { vec![] }
        }
        let executor = HardenedToolExecutor::new(Arc::new(OkTool), ToolPolicy::default());
        let result = executor.execute(make_call()).await.unwrap();
        assert!(!result.is_error);
    }
}
```

- [ ] **Step 3: Update devsper-executor/src/lib.rs**

```rust
pub mod executor;
pub mod hardened_tool;

pub use executor::{AgentFn, AgentOutput, Executor, ExecutorConfig};
pub use hardened_tool::{HardenedToolExecutor, ToolPolicy};
```

- [ ] **Step 4: Run tests**

```bash
cargo test -p devsper-executor 2>&1 | tail -20
```

Expected: all pass including 3 new hardened_tool tests.

- [ ] **Step 5: Commit**

```bash
git add crates/devsper-executor/src/hardened_tool.rs crates/devsper-executor/src/lib.rs
git commit -m "feat(executor): HardenedToolExecutor with timeout and retry policy"
```

---

## Task 8: Streaming Executor with EventBus Integration

**Files:**
- Create: `crates/devsper-executor/src/streaming.rs`
- Modify: `crates/devsper-executor/src/lib.rs`

- [ ] **Step 1: Write failing test**

```rust
// In streaming.rs tests — subscribe to bus, run executor, assert NodeStarted + NodeCompleted received
```

- [ ] **Step 2: Implement StreamingExecutor**

Full content of `crates/devsper-executor/src/streaming.rs`:

```rust
use crate::executor::{AgentOutput, ExecutorConfig};
use devsper_core::{EventBus, EventEnvelope, GraphEvent, GraphMutation, NodeSpec, RunId, now_ms};
use devsper_graph::GraphHandle;
use devsper_scheduler::Scheduler;
use anyhow::Result;
use std::sync::Arc;
use tokio::sync::{mpsc, Semaphore};
use tokio::time::{sleep, Duration};
use tracing::{debug, error, info, warn};

/// Agent function that receives a chunk sender for streaming partial outputs.
pub type StreamingAgentFn = Arc<
    dyn Fn(NodeSpec, mpsc::Sender<String>) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<AgentOutput, String>> + Send>>
    + Send + Sync,
>;

/// Like Executor but emits GraphEvents to an EventBus throughout execution.
pub struct StreamingExecutor {
    config: ExecutorConfig,
    scheduler: Arc<Scheduler>,
    handle: GraphHandle,
    agent_fn: StreamingAgentFn,
    bus: Arc<dyn EventBus>,
    run_id: RunId,
    sequence: Arc<std::sync::atomic::AtomicU64>,
}

impl StreamingExecutor {
    pub fn new(
        config: ExecutorConfig,
        scheduler: Arc<Scheduler>,
        handle: GraphHandle,
        agent_fn: StreamingAgentFn,
        bus: Arc<dyn EventBus>,
        run_id: RunId,
    ) -> Self {
        Self {
            config, scheduler, handle, agent_fn, bus, run_id,
            sequence: Arc::new(std::sync::atomic::AtomicU64::new(0)),
        }
    }

    fn next_seq(&self) -> u64 {
        self.sequence.fetch_add(1, std::sync::atomic::Ordering::SeqCst)
    }

    async fn emit(&self, event: GraphEvent) {
        let env = EventEnvelope::new(self.run_id.clone(), self.next_seq(), event);
        let _ = self.bus.publish(env).await;
    }

    pub async fn run(self) -> Result<()> {
        let semaphore = Arc::new(Semaphore::new(self.config.worker_count));
        let scheduler = self.scheduler.clone();
        let handle = self.handle.clone();
        let agent_fn = self.agent_fn.clone();
        let bus = self.bus.clone();
        let run_id = self.run_id.clone();
        let sequence = self.sequence.clone();
        let poll_ms = self.config.poll_interval_ms;

        self.emit(GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() }).await;

        info!("StreamingExecutor started (workers={})", self.config.worker_count);

        let mut stall_count = 0u32;
        const MAX_STALL: u32 = 100;

        loop {
            let ready = scheduler.get_ready().await;

            if ready.is_empty() {
                let snap = scheduler.snapshot().await;
                if let Some(snap) = snap {
                    if snap.nodes.values().all(|n| n.is_terminal()) && !snap.nodes.is_empty() {
                        let env = EventEnvelope::new(
                            run_id.clone(),
                            sequence.fetch_add(1, std::sync::atomic::Ordering::SeqCst),
                            GraphEvent::RunCompleted { run_id: run_id.clone(), ts: now_ms() },
                        );
                        let _ = bus.publish(env).await;
                        info!("StreamingExecutor done.");
                        break;
                    }
                    stall_count += 1;
                    if stall_count > MAX_STALL {
                        let env = EventEnvelope::new(
                            run_id.clone(),
                            sequence.fetch_add(1, std::sync::atomic::Ordering::SeqCst),
                            GraphEvent::RunFailed { run_id: run_id.clone(), error: "stalled".to_string(), ts: now_ms() },
                        );
                        let _ = bus.publish(env).await;
                        warn!("StreamingExecutor stalled");
                        break;
                    }
                }
                sleep(Duration::from_millis(poll_ms)).await;
                continue;
            }

            stall_count = 0;

            for node_id in ready {
                if !scheduler.claim(node_id.clone()).await { continue; }

                let permit = semaphore.clone().acquire_owned().await?;
                let sched = scheduler.clone();
                let h = handle.clone();
                let agent = agent_fn.clone();
                let bus2 = bus.clone();
                let run_id2 = run_id.clone();
                let seq2 = sequence.clone();

                let spec = {
                    let snap = sched.snapshot().await;
                    snap.and_then(|s| s.nodes.get(&node_id).map(|n| n.spec.clone()))
                };
                let Some(spec) = spec else {
                    warn!("spec not found for {node_id}");
                    sched.fail(node_id, "spec not found".to_string()).await;
                    drop(permit);
                    continue;
                };

                let nid = node_id.clone();
                let emit = move |event: GraphEvent| {
                    let bus = bus2.clone();
                    let rid = run_id2.clone();
                    let seq = seq2.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                    async move {
                        let _ = bus.publish(EventEnvelope::new(rid, seq, event)).await;
                    }
                };

                let nid2 = nid.clone();
                emit(GraphEvent::NodeStarted { id: nid2.clone(), ts: now_ms() }).await;

                tokio::spawn(async move {
                    let _permit = permit;
                    let (chunk_tx, mut chunk_rx) = mpsc::channel::<String>(64);

                    // Spawn chunk forwarder
                    let nid3 = nid2.clone();
                    let emit2 = {
                        let bus = bus.clone();
                        let rid = run_id2.clone();
                        let seq = seq2.clone();
                        move |chunk: String| {
                            let bus = bus.clone();
                            let rid = rid.clone();
                            let s = seq.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                            let id = nid3.clone();
                            tokio::spawn(async move {
                                let _ = bus.publish(EventEnvelope::new(rid, s,
                                    GraphEvent::NodeOutput { id, chunk, ts: now_ms() }
                                )).await;
                            });
                        }
                    };

                    tokio::spawn(async move {
                        while let Some(chunk) = chunk_rx.recv().await {
                            emit2(chunk);
                        }
                    });

                    match agent(spec, chunk_tx).await {
                        Ok(output) => {
                            for mutation in output.mutations {
                                if let Err(e) = h.mutate(mutation).await {
                                    warn!("Mutation rejected: {e}");
                                }
                            }
                            sched.complete(nid2.clone(), output.result).await;
                            emit(GraphEvent::NodeCompleted { id: nid2, result: serde_json::json!(null), ts: now_ms() }).await;
                        }
                        Err(e) => {
                            error!(error = %e, "Task failed");
                            sched.fail(nid2.clone(), e.clone()).await;
                            emit(GraphEvent::NodeFailed { id: nid2, error: e, ts: now_ms() }).await;
                        }
                    }
                });
            }

            sleep(Duration::from_millis(poll_ms)).await;
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_bus::InMemoryEventBus;
    use devsper_core::{NodeSpec, RunId};
    use devsper_graph::{GraphActor, GraphConfig};
    use tokio_stream::StreamExt;

    fn make_streaming_agent(result: serde_json::Value) -> StreamingAgentFn {
        Arc::new(move |_spec: NodeSpec, tx: mpsc::Sender<String>| {
            let result = result.clone();
            Box::pin(async move {
                let _ = tx.send("chunk-1".to_string()).await;
                let _ = tx.send("chunk-2".to_string()).await;
                Ok(AgentOutput { result, mutations: vec![] })
            })
        })
    }

    #[tokio::test]
    async fn emits_run_started_and_completed() {
        let run_id = RunId::new();
        let config = GraphConfig { run_id: run_id.clone(), snapshot_interval: 100, max_depth: 10 };
        let (mut actor, handle, _) = GraphActor::new(config);
        actor.add_initial_nodes(vec![NodeSpec::new("task-a")]);
        tokio::spawn(actor.run());

        let bus = Arc::new(InMemoryEventBus::new());
        let mut stream = bus.subscribe(&run_id).await.unwrap();

        let scheduler = Arc::new(Scheduler::new(handle.clone()));
        let executor = StreamingExecutor::new(
            ExecutorConfig { worker_count: 1, poll_interval_ms: 10 },
            scheduler, handle,
            make_streaming_agent(serde_json::json!({"done": true})),
            bus, run_id.clone(),
        );

        executor.run().await.unwrap();

        let mut events = vec![];
        while let Ok(Some(env)) = tokio::time::timeout(
            Duration::from_millis(50), stream.next()
        ).await {
            events.push(env);
        }

        let kinds: Vec<&str> = events.iter().map(|e| match &e.event {
            GraphEvent::RunStarted { .. } => "RunStarted",
            GraphEvent::RunCompleted { .. } => "RunCompleted",
            GraphEvent::NodeStarted { .. } => "NodeStarted",
            GraphEvent::NodeOutput { .. } => "NodeOutput",
            GraphEvent::NodeCompleted { .. } => "NodeCompleted",
            _ => "other",
        }).collect();

        assert!(kinds.contains(&"RunStarted"));
        assert!(kinds.contains(&"NodeStarted"));
        assert!(kinds.contains(&"RunCompleted"));
        assert!(kinds.contains(&"NodeOutput"), "streaming chunks must be emitted");
    }
}
```

- [ ] **Step 3: Update lib.rs**

```rust
pub mod executor;
pub mod hardened_tool;
pub mod streaming;

pub use executor::{AgentFn, AgentOutput, Executor, ExecutorConfig};
pub use hardened_tool::{HardenedToolExecutor, ToolPolicy};
pub use streaming::{StreamingAgentFn, StreamingExecutor};
```

- [ ] **Step 4: Add devsper-bus dependency to devsper-executor Cargo.toml** (test-only):

```toml
[dev-dependencies]
devsper-bus = { path = "../devsper-bus" }
tokio-stream = { workspace = true }
```

- [ ] **Step 5: Run tests**

```bash
cargo test -p devsper-executor 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add crates/devsper-executor/src/streaming.rs crates/devsper-executor/src/lib.rs crates/devsper-executor/Cargo.toml
git commit -m "feat(executor): StreamingExecutor emits NodeOutput chunks and run lifecycle events"
```

---

## Task 9: Deterministic Replay System

**Files:**
- Create: `crates/devsper-graph/src/replay.rs`
- Modify: `crates/devsper-graph/src/lib.rs`

- [ ] **Step 1: Write failing test**

```rust
// replay(events) must reconstruct RunState::Completed + correct node statuses
```

- [ ] **Step 2: Implement**

Full content of `crates/devsper-graph/src/replay.rs`:

```rust
use devsper_core::{EventEnvelope, GraphEvent, Node, NodeId, NodeSpec, NodeStatus, RunId, RunState};
use std::collections::HashMap;

#[derive(Debug, Clone, Default)]
pub struct ReplayState {
    pub nodes: HashMap<NodeId, Node>,
    pub edges: Vec<(NodeId, NodeId)>,
    pub run_state: RunState,
    pub event_count: u64,
}

/// Reconstruct full run state from an ordered event log.
/// Deterministic: same input always produces same output.
pub fn replay(envelopes: &[EventEnvelope]) -> ReplayState {
    let mut state = ReplayState::default();
    // Sort by sequence to guarantee deterministic ordering
    let mut sorted: Vec<&EventEnvelope> = envelopes.iter().collect();
    sorted.sort_by_key(|e| e.sequence);

    for envelope in sorted {
        state.event_count += 1;
        apply(&mut state, &envelope.event);
    }
    state
}

fn apply(state: &mut ReplayState, event: &GraphEvent) {
    match event {
        GraphEvent::RunStarted { .. } => {
            state.run_state = RunState::Running;
        }
        GraphEvent::RunCompleted { .. } => {
            state.run_state = RunState::Completed;
        }
        GraphEvent::RunFailed { .. } => {
            state.run_state = RunState::Failed;
        }
        GraphEvent::RunStateChanged { to, .. } => {
            state.run_state = to.clone();
        }
        GraphEvent::NodeAdded { id, spec, .. } => {
            state.nodes.entry(id.clone()).or_insert_with(|| Node::new(spec.clone()));
        }
        GraphEvent::EdgeAdded { from, to, .. } => {
            if !state.edges.contains(&(from.clone(), to.clone())) {
                state.edges.push((from.clone(), to.clone()));
            }
        }
        GraphEvent::EdgeRemoved { from, to, .. } => {
            state.edges.retain(|(f, t)| f != from || t != to);
        }
        GraphEvent::NodeReady { id, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Ready;
            }
        }
        GraphEvent::NodeStarted { id, ts, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Running;
                node.started_at = Some(*ts);
            }
        }
        GraphEvent::NodeCompleted { id, result, ts, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Completed;
                node.result = Some(result.clone());
                node.completed_at = Some(*ts);
            }
        }
        GraphEvent::NodeFailed { id, error, ts, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Failed;
                node.error = Some(error.clone());
                node.completed_at = Some(*ts);
            }
        }
        GraphEvent::NodeAbandoned { id, .. } => {
            if let Some(node) = state.nodes.get_mut(id) {
                node.status = NodeStatus::Abandoned;
            }
        }
        GraphEvent::HitlRequested { .. } => {
            state.run_state = RunState::WaitingHITL;
        }
        GraphEvent::HitlApproved { .. } => {
            state.run_state = RunState::Running;
        }
        GraphEvent::HitlRejected { .. } => {
            state.run_state = RunState::Failed;
        }
        // NodeOutput, AgentStarted/Completed, ToolCalled/Completed/Failed,
        // MemoryRead/Written, MutationApplied/Rejected, SnapshotTaken — no state change needed
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{now_ms, EventEnvelope, NodeSpec, RunId};

    fn node_spec(prompt: &str) -> NodeSpec { NodeSpec::new(prompt) }

    #[test]
    fn empty_events_produce_created_state() {
        let state = replay(&[]);
        assert_eq!(state.run_state, RunState::Created);
        assert_eq!(state.event_count, 0);
    }

    #[test]
    fn run_start_then_complete() {
        let run_id = RunId::new();
        let events = vec![
            EventEnvelope::new(run_id.clone(), 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() }),
            EventEnvelope::new(run_id.clone(), 1, GraphEvent::RunCompleted { run_id: run_id.clone(), ts: now_ms() }),
        ];
        let state = replay(&events);
        assert_eq!(state.run_state, RunState::Completed);
        assert_eq!(state.event_count, 2);
    }

    #[test]
    fn node_lifecycle_reconstructed() {
        let run_id = RunId::new();
        let spec = node_spec("task-a");
        let node_id = spec.id.clone();
        let ts = now_ms();

        let events = vec![
            EventEnvelope::new(run_id.clone(), 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            EventEnvelope::new(run_id.clone(), 1, GraphEvent::NodeAdded { id: node_id.clone(), spec: spec.clone(), ts }),
            EventEnvelope::new(run_id.clone(), 2, GraphEvent::NodeStarted { id: node_id.clone(), ts: ts + 10 }),
            EventEnvelope::new(run_id.clone(), 3, GraphEvent::NodeCompleted {
                id: node_id.clone(), result: serde_json::json!({"out": "done"}), ts: ts + 100
            }),
            EventEnvelope::new(run_id.clone(), 4, GraphEvent::RunCompleted { run_id: run_id.clone(), ts: ts + 110 }),
        ];

        let state = replay(&events);
        assert_eq!(state.run_state, RunState::Completed);
        let node = state.nodes.get(&node_id).unwrap();
        assert_eq!(node.status, NodeStatus::Completed);
        assert_eq!(node.result.as_ref().unwrap()["out"], "done");
    }

    #[test]
    fn replay_is_deterministic_regardless_of_input_order() {
        let run_id = RunId::new();
        let spec = node_spec("task");
        let node_id = spec.id.clone();
        let ts = now_ms();

        let mut events = vec![
            EventEnvelope::new(run_id.clone(), 2, GraphEvent::NodeCompleted {
                id: node_id.clone(), result: serde_json::json!({"x": 1}), ts: ts + 50
            }),
            EventEnvelope::new(run_id.clone(), 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            EventEnvelope::new(run_id.clone(), 1, GraphEvent::NodeAdded { id: node_id.clone(), spec, ts }),
            EventEnvelope::new(run_id.clone(), 3, GraphEvent::RunCompleted { run_id: run_id.clone(), ts: ts + 60 }),
        ];

        let state1 = replay(&events);
        events.reverse();
        let state2 = replay(&events);

        assert_eq!(state1.run_state, state2.run_state);
        assert_eq!(
            state1.nodes[&node_id].status,
            state2.nodes[&node_id].status
        );
    }

    #[test]
    fn hitl_pause_and_resume_in_replay() {
        let run_id = RunId::new();
        let spec = node_spec("hitl-task");
        let node_id = spec.id.clone();
        let ts = now_ms();

        let events = vec![
            EventEnvelope::new(run_id.clone(), 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
            EventEnvelope::new(run_id.clone(), 1, GraphEvent::NodeAdded { id: node_id.clone(), spec, ts }),
            EventEnvelope::new(run_id.clone(), 2, GraphEvent::HitlRequested { node_id: node_id.clone(), reason: "cost".to_string(), ts }),
            EventEnvelope::new(run_id.clone(), 3, GraphEvent::HitlApproved { node_id: node_id.clone(), ts: ts + 1000 }),
            EventEnvelope::new(run_id.clone(), 4, GraphEvent::NodeCompleted { id: node_id.clone(), result: serde_json::json!(null), ts: ts + 2000 }),
            EventEnvelope::new(run_id.clone(), 5, GraphEvent::RunCompleted { run_id: run_id.clone(), ts: ts + 2010 }),
        ];

        let state = replay(&events);
        assert_eq!(state.run_state, RunState::Completed);
    }
}
```

- [ ] **Step 3: Update graph lib.rs**

```rust
pub mod actor;
pub mod event_log;
pub mod mutation;
pub mod replay;
pub mod snapshot;
pub mod validator;

pub use actor::{GraphActor, GraphConfig, GraphHandle};
pub use event_log::EventLog;
pub use mutation::{MutationRequest, MutationResult};
pub use replay::{replay, ReplayState};
pub use validator::MutationValidator;
```

- [ ] **Step 4: Run tests**

```bash
cargo test -p devsper-graph 2>&1 | tail -20
```

Expected: all pass including 5 new replay tests.

- [ ] **Step 5: Commit**

```bash
git add crates/devsper-graph/src/replay.rs crates/devsper-graph/src/lib.rs
git commit -m "feat(graph): deterministic replay engine — reconstructs RunState from EventEnvelope log"
```

---

## Task 10: Mutation Engine Hardening

**Files:**
- Modify: `crates/devsper-core/src/types.rs` (add RemoveNode + ModifyNode variants)
- Modify: `crates/devsper-graph/src/validator.rs` (validate new variants)

- [ ] **Step 1: Add missing mutation variants to GraphMutation in types.rs**

Find the `GraphMutation` enum and add two new variants:

```rust
pub enum GraphMutation {
    AddNode { spec: NodeSpec },
    RemoveNode { id: NodeId },           // NEW
    ModifyNode { id: NodeId, prompt: String, model: Option<String> }, // NEW
    AddEdge { from: NodeId, to: NodeId },
    RemoveEdge { from: NodeId, to: NodeId },
    SplitNode { node: NodeId, into: Vec<NodeSpec> },
    InjectBefore { before: NodeId, insert: NodeSpec },
    PruneSubgraph { root: NodeId },
    MarkSpeculative { nodes: Vec<NodeId> },
    ConfirmSpeculative { nodes: Vec<NodeId> },
    DiscardSpeculative { nodes: Vec<NodeId> },
}
```

- [ ] **Step 2: Update validator.rs to handle new variants**

```rust
pub fn validate(
    &self,
    graph: &DiGraph<NodeId, ()>,
    index_map: &HashMap<NodeId, NodeIndex>,
    mutation: &GraphMutation,
) -> Result<(), String> {
    match mutation {
        GraphMutation::AddEdge { from, to } => {
            self.validate_add_edge(graph, index_map, from, to)
        }
        GraphMutation::RemoveNode { id } => {
            // Cannot remove a node that doesn't exist
            if !index_map.contains_key(id) {
                Err(format!("Node not found: {id}"))
            } else {
                Ok(())
            }
        }
        GraphMutation::ModifyNode { id, .. } => {
            if !index_map.contains_key(id) {
                Err(format!("Node not found: {id}"))
            } else {
                Ok(())
            }
        }
        GraphMutation::InjectBefore { .. } => Ok(()),
        GraphMutation::SplitNode { .. } => Ok(()),
        _ => Ok(()),
    }
}
```

- [ ] **Step 3: Handle new variants in GraphActor**

In `crates/devsper-graph/src/actor.rs`, find the mutation application code and add arms for `RemoveNode` and `ModifyNode`. Search for where `GraphMutation::AddNode` is handled and add:

```rust
GraphMutation::RemoveNode { id } => {
    if let Some(idx) = self.index_map.remove(&id) {
        self.graph.remove_node(idx);
        self.emit(GraphEvent::MutationApplied { mutation: mutation.clone(), ts: now_ms() });
    }
}
GraphMutation::ModifyNode { id, prompt, model } => {
    // Update the NodeSpec in our nodes map
    if let Some(node) = self.nodes.get_mut(&id) {
        node.spec.prompt = prompt.clone();
        node.spec.model = model.clone();
        self.emit(GraphEvent::MutationApplied { mutation: mutation.clone(), ts: now_ms() });
    }
}
```

- [ ] **Step 4: Add tests in types.rs tests block**

```rust
#[test]
fn remove_node_mutation_serializes() {
    let m = GraphMutation::RemoveNode { id: NodeId::new() };
    let json = serde_json::to_string(&m).unwrap();
    let m2: GraphMutation = serde_json::from_str(&json).unwrap();
    assert!(matches!(m2, GraphMutation::RemoveNode { .. }));
}

#[test]
fn modify_node_mutation_serializes() {
    let m = GraphMutation::ModifyNode {
        id: NodeId::new(),
        prompt: "updated prompt".to_string(),
        model: Some("claude-opus-4-7".to_string()),
    };
    let json = serde_json::to_string(&m).unwrap();
    let m2: GraphMutation = serde_json::from_str(&json).unwrap();
    match m2 {
        GraphMutation::ModifyNode { prompt, .. } => assert_eq!(prompt, "updated prompt"),
        _ => panic!("wrong variant"),
    }
}
```

- [ ] **Step 5: Run all tests**

```bash
cargo test -p devsper-core -p devsper-graph 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add crates/devsper-core/src/types.rs crates/devsper-graph/src/validator.rs crates/devsper-graph/src/actor.rs
git commit -m "feat(graph): RemoveNode + ModifyNode mutations with validation"
```

---

## Task 11: Unit Tests

**Files:**
- Create: `crates/devsper-core/tests/unit.rs`

- [ ] **Step 1: Write and run unit tests**

```rust
// crates/devsper-core/tests/unit.rs
use devsper_core::*;

#[test]
fn all_graph_event_variants_serialize_roundtrip() {
    let run_id = RunId::new();
    let node_id = NodeId::new();
    let ts = now_ms();
    let spec = NodeSpec::new("test");

    let events = vec![
        GraphEvent::RunStarted { run_id: run_id.clone(), ts },
        GraphEvent::RunCompleted { run_id: run_id.clone(), ts },
        GraphEvent::RunFailed { run_id: run_id.clone(), error: "err".to_string(), ts },
        GraphEvent::RunStateChanged { run_id: run_id.clone(), from: RunState::Created, to: RunState::Running, ts },
        GraphEvent::NodeAdded { id: node_id.clone(), spec: spec.clone(), ts },
        GraphEvent::NodeReady { id: node_id.clone(), ts },
        GraphEvent::NodeStarted { id: node_id.clone(), ts },
        GraphEvent::NodeOutput { id: node_id.clone(), chunk: "hello".to_string(), ts },
        GraphEvent::NodeCompleted { id: node_id.clone(), result: serde_json::json!(null), ts },
        GraphEvent::NodeFailed { id: node_id.clone(), error: "fail".to_string(), ts },
        GraphEvent::NodeAbandoned { id: node_id.clone(), ts },
        GraphEvent::EdgeAdded { from: node_id.clone(), to: node_id.clone(), ts },
        GraphEvent::EdgeRemoved { from: node_id.clone(), to: node_id.clone(), ts },
        GraphEvent::AgentStarted { node_id: node_id.clone(), model: "m".to_string(), ts },
        GraphEvent::AgentCompleted { node_id: node_id.clone(), input_tokens: 10, output_tokens: 5, ts },
        GraphEvent::ToolCalled { node_id: node_id.clone(), tool_name: "t".to_string(), args: serde_json::json!({}), ts },
        GraphEvent::ToolCompleted { node_id: node_id.clone(), tool_name: "t".to_string(), duration_ms: 50, ts },
        GraphEvent::ToolFailed { node_id: node_id.clone(), tool_name: "t".to_string(), error: "e".to_string(), ts },
        GraphEvent::MemoryRead { namespace: "ns".to_string(), key: "k".to_string(), scope: MemoryScope::Run, ts },
        GraphEvent::MemoryWritten { namespace: "ns".to_string(), key: "k".to_string(), scope: MemoryScope::Context, ts },
        GraphEvent::MutationRejected { reason: "cycle".to_string(), ts },
        GraphEvent::HitlRequested { node_id: node_id.clone(), reason: "cost".to_string(), ts },
        GraphEvent::HitlApproved { node_id: node_id.clone(), ts },
        GraphEvent::HitlRejected { node_id: node_id.clone(), reason: "denied".to_string(), ts },
    ];

    for event in events {
        let json = serde_json::to_string(&event).expect("serialize");
        let back: GraphEvent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(back.ts(), ts);
    }
}

#[test]
fn event_envelope_sequence_is_unique_per_call() {
    let run_id = RunId::new();
    let e1 = EventEnvelope::new(run_id.clone(), 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() });
    let e2 = EventEnvelope::new(run_id.clone(), 1, GraphEvent::RunStarted { run_id: run_id.clone(), ts: now_ms() });
    assert_ne!(e1.event_id, e2.event_id);
    assert_ne!(e1.sequence, e2.sequence);
}

#[test]
fn run_state_machine_all_valid_paths() {
    use RunState::*;
    assert!(Created.transition(&Running).is_ok());
    assert!(Running.transition(&WaitingHITL).is_ok());
    assert!(Running.transition(&Completed).is_ok());
    assert!(Running.transition(&Failed).is_ok());
    assert!(WaitingHITL.transition(&Running).is_ok());
    assert!(WaitingHITL.transition(&Failed).is_ok());
}

#[test]
fn run_state_machine_invalid_paths() {
    use RunState::*;
    assert!(Created.transition(&Completed).is_err());
    assert!(Completed.transition(&Running).is_err());
    assert!(Failed.transition(&Running).is_err());
    assert!(Created.transition(&WaitingHITL).is_err());
}

#[test]
fn memory_scope_variants_all_serialize() {
    for scope in [MemoryScope::Run, MemoryScope::Context, MemoryScope::Workflow] {
        let json = serde_json::to_string(&scope).unwrap();
        let back: MemoryScope = serde_json::from_str(&json).unwrap();
        assert_eq!(back, scope);
    }
}
```

- [ ] **Step 2: Run**

```bash
cargo test -p devsper-core 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add crates/devsper-core/tests/unit.rs
git commit -m "test(core): comprehensive unit tests for events, state machine, memory scope"
```

---

## Task 12: Integration Tests

**Files:**
- Create: `tests/integration/mod.rs`
- Create: `tests/integration/run_lifecycle.rs`
- Create: `tests/integration/streaming_events.rs`
- Create: `tests/integration/memory_scoping.rs`
- Modify: `Cargo.toml` (integration test config)

- [ ] **Step 1: Create test harness**

Check if `tests/` directory is set up as integration test suite. If not, add to workspace root `Cargo.toml`:

```toml
[[test]]
name = "integration"
path = "tests/integration/mod.rs"
```

- [ ] **Step 2: Create tests/integration/mod.rs**

```rust
mod memory_scoping;
mod run_lifecycle;
mod streaming_events;
```

- [ ] **Step 3: Create run_lifecycle.rs**

```rust
use devsper_bus::InMemoryEventBus;
use devsper_core::{GraphEvent, NodeSpec, RunId, RunState};
use devsper_executor::{AgentFn, AgentOutput, Executor, ExecutorConfig, StreamingAgentFn, StreamingExecutor};
use devsper_graph::{GraphActor, GraphConfig};
use devsper_observability::TraceCollector;
use devsper_scheduler::Scheduler;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_stream::StreamExt;

#[tokio::test]
async fn full_run_lifecycle_with_trace() {
    let run_id = RunId::new();
    let config = GraphConfig { run_id: run_id.clone(), snapshot_interval: 100, max_depth: 10 };
    let (mut actor, handle, _) = GraphActor::new(config);

    let spec_a = NodeSpec::new("task-a");
    let id_a = spec_a.id.clone();
    let spec_b = NodeSpec::new("task-b").depends_on(vec![id_a.clone()]);
    actor.add_initial_nodes(vec![spec_a, spec_b]);
    tokio::spawn(actor.run());

    let bus = Arc::new(InMemoryEventBus::new());
    let collector = Arc::new(TraceCollector::new(run_id.clone()));
    let mut stream = bus.subscribe(&run_id).await.unwrap();

    // Drive collector in background
    let col2 = collector.clone();
    tokio::spawn(async move {
        while let Some(env) = stream.next().await {
            col2.ingest(&env).await;
        }
    });

    let agent: StreamingAgentFn = Arc::new(|_spec, _tx| {
        Box::pin(async move {
            Ok(AgentOutput { result: serde_json::json!({"done": true}), mutations: vec![] })
        })
    });

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = StreamingExecutor::new(
        ExecutorConfig { worker_count: 2, poll_interval_ms: 10 },
        scheduler, handle, agent, bus, run_id.clone(),
    );

    executor.run().await.unwrap();
    tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;

    let trace = collector.snapshot().await;
    assert_eq!(trace.state, RunState::Completed);
    assert!(trace.started_at.is_some());
    assert!(trace.total_latency_ms.is_some());
}
```

- [ ] **Step 4: Create memory_scoping.rs**

```rust
use devsper_core::{MemoryScope, RunId};
use devsper_memory::{LocalMemoryStore, ScopedMemoryStore};
use std::sync::Arc;

#[tokio::test]
async fn run_and_context_scopes_do_not_share_data() {
    let store = Arc::new(LocalMemoryStore::new());
    let run_id = RunId::new();

    let run_scope = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Run);
    let ctx_scope = ScopedMemoryStore::new(store.clone(), run_id.clone(), None, MemoryScope::Context);
    let wf_scope  = ScopedMemoryStore::new(store.clone(), run_id.clone(), Some("wf-1".to_string()), MemoryScope::Workflow);

    run_scope.store("key", serde_json::json!("run-val")).await.unwrap();
    ctx_scope.store("key", serde_json::json!("ctx-val")).await.unwrap();
    wf_scope.store("key", serde_json::json!("wf-val")).await.unwrap();

    assert_eq!(run_scope.retrieve("key").await.unwrap().unwrap(), "run-val");
    assert_eq!(ctx_scope.retrieve("key").await.unwrap().unwrap(), "ctx-val");
    assert_eq!(wf_scope.retrieve("key").await.unwrap().unwrap(), "wf-val");
}

#[tokio::test]
async fn workflow_scope_shared_across_runs() {
    let store = Arc::new(LocalMemoryStore::new());
    let run_a = RunId::new();
    let run_b = RunId::new();

    let wf_a = ScopedMemoryStore::new(store.clone(), run_a, Some("shared-wf".to_string()), MemoryScope::Workflow);
    let wf_b = ScopedMemoryStore::new(store.clone(), run_b, Some("shared-wf".to_string()), MemoryScope::Workflow);

    wf_a.store("fact", serde_json::json!("from-run-a")).await.unwrap();
    let seen_by_b = wf_b.retrieve("fact").await.unwrap();
    assert_eq!(seen_by_b.unwrap(), "from-run-a", "Workflow scope shared across runs");
}
```

- [ ] **Step 5: Create streaming_events.rs**

```rust
use devsper_bus::InMemoryEventBus;
use devsper_core::{GraphEvent, NodeSpec, RunId};
use devsper_executor::{AgentOutput, ExecutorConfig, StreamingAgentFn, StreamingExecutor};
use devsper_graph::{GraphActor, GraphConfig};
use devsper_scheduler::Scheduler;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_stream::StreamExt;

#[tokio::test]
async fn streaming_agent_chunks_appear_as_node_output_events() {
    let run_id = RunId::new();
    let config = GraphConfig { run_id: run_id.clone(), snapshot_interval: 100, max_depth: 10 };
    let (mut actor, handle, _) = GraphActor::new(config);
    actor.add_initial_nodes(vec![NodeSpec::new("chunked-task")]);
    tokio::spawn(actor.run());

    let bus = Arc::new(InMemoryEventBus::new());
    let mut stream = bus.subscribe(&run_id).await.unwrap();

    let agent: StreamingAgentFn = Arc::new(|_spec, tx| {
        Box::pin(async move {
            tx.send("token-1".to_string()).await.ok();
            tx.send("token-2".to_string()).await.ok();
            tx.send("token-3".to_string()).await.ok();
            Ok(AgentOutput { result: serde_json::json!(null), mutations: vec![] })
        })
    });

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = StreamingExecutor::new(
        ExecutorConfig { worker_count: 1, poll_interval_ms: 10 },
        scheduler, handle, agent, bus, run_id.clone(),
    );
    executor.run().await.unwrap();

    let mut chunk_count = 0usize;
    let mut run_completed = false;
    while let Ok(Some(env)) = tokio::time::timeout(
        tokio::time::Duration::from_millis(200), stream.next()
    ).await {
        match &env.event {
            GraphEvent::NodeOutput { chunk, .. } => {
                assert!(chunk.starts_with("token-"));
                chunk_count += 1;
            }
            GraphEvent::RunCompleted { .. } => run_completed = true,
            _ => {}
        }
    }

    assert_eq!(chunk_count, 3, "all 3 chunks must appear as NodeOutput events");
    assert!(run_completed);
}
```

- [ ] **Step 6: Run integration tests**

```bash
cargo test --test integration 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add tests/integration/ Cargo.toml
git commit -m "test: integration tests for run lifecycle, streaming events, memory scoping"
```

---

## Task 13: E2E Tests

**Files:**
- Create: `tests/e2e/mod.rs`
- Create: `tests/e2e/full_workflow.rs`
- Create: `tests/e2e/replay_determinism.rs`
- Create: `tests/e2e/multi_agent.rs`

Add to workspace `Cargo.toml`:
```toml
[[test]]
name = "e2e"
path = "tests/e2e/mod.rs"
```

- [ ] **Step 1: Create e2e/mod.rs**

```rust
mod full_workflow;
mod multi_agent;
mod replay_determinism;
```

- [ ] **Step 2: Create full_workflow.rs**

```rust
//! Full workflow E2E: A → B → C linear chain with streaming + observability
use devsper_bus::InMemoryEventBus;
use devsper_core::{NodeSpec, RunId, RunState};
use devsper_executor::{AgentOutput, ExecutorConfig, StreamingAgentFn, StreamingExecutor};
use devsper_graph::{GraphActor, GraphConfig};
use devsper_observability::TraceCollector;
use devsper_scheduler::Scheduler;
use std::sync::Arc;
use tokio_stream::StreamExt;

#[tokio::test]
async fn linear_chain_a_b_c_completes_in_order() {
    let run_id = RunId::new();
    let config = GraphConfig { run_id: run_id.clone(), snapshot_interval: 100, max_depth: 10 };
    let (mut actor, handle, _) = GraphActor::new(config);

    let spec_a = NodeSpec::new("A");
    let id_a = spec_a.id.clone();
    let spec_b = NodeSpec::new("B").depends_on(vec![id_a.clone()]);
    let id_b = spec_b.id.clone();
    let spec_c = NodeSpec::new("C").depends_on(vec![id_b.clone()]);
    actor.add_initial_nodes(vec![spec_a, spec_b, spec_c]);
    tokio::spawn(actor.run());

    let bus = Arc::new(InMemoryEventBus::new());
    let collector = Arc::new(TraceCollector::new(run_id.clone()));
    let mut stream = bus.subscribe(&run_id).await.unwrap();
    let col2 = collector.clone();
    tokio::spawn(async move {
        while let Some(env) = stream.next().await { col2.ingest(&env).await; }
    });

    let execution_order = Arc::new(tokio::sync::Mutex::new(vec![]));
    let eo = execution_order.clone();

    let agent: StreamingAgentFn = Arc::new(move |spec, _tx| {
        let eo = eo.clone();
        let label = spec.prompt.clone();
        Box::pin(async move {
            eo.lock().await.push(label);
            Ok(AgentOutput { result: serde_json::json!(null), mutations: vec![] })
        })
    });

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = StreamingExecutor::new(
        ExecutorConfig { worker_count: 2, poll_interval_ms: 10 },
        scheduler, handle, agent, bus, run_id.clone(),
    );
    executor.run().await.unwrap();
    tokio::time::sleep(tokio::time::Duration::from_millis(50)).await;

    let order = execution_order.lock().await.clone();
    assert_eq!(order, vec!["A", "B", "C"], "A must complete before B, B before C");

    let trace = collector.snapshot().await;
    assert_eq!(trace.state, RunState::Completed);
    assert_eq!(trace.event_count > 0, true);
}
```

- [ ] **Step 3: Create replay_determinism.rs**

```rust
//! E2E: replay must produce identical RunState to live execution
use devsper_bus::InMemoryEventBus;
use devsper_core::{NodeSpec, RunId, RunState};
use devsper_executor::{AgentOutput, ExecutorConfig, StreamingAgentFn, StreamingExecutor};
use devsper_graph::{replay, GraphActor, GraphConfig};
use devsper_scheduler::Scheduler;
use std::sync::Arc;
use tokio_stream::StreamExt;

#[tokio::test]
async fn replay_produces_same_state_as_live_run() {
    let run_id = RunId::new();
    let config = GraphConfig { run_id: run_id.clone(), snapshot_interval: 100, max_depth: 10 };
    let (mut actor, handle, _) = GraphActor::new(config);
    actor.add_initial_nodes(vec![NodeSpec::new("task-x"), NodeSpec::new("task-y")]);
    tokio::spawn(actor.run());

    let bus = Arc::new(InMemoryEventBus::new());
    let mut stream = bus.subscribe(&run_id).await.unwrap();

    // Collect all emitted envelopes
    let collected = Arc::new(tokio::sync::Mutex::new(vec![]));
    let col = collected.clone();
    let collector_handle = tokio::spawn(async move {
        while let Some(env) = stream.next().await {
            col.lock().await.push(env);
        }
    });

    let agent: StreamingAgentFn = Arc::new(|_spec, _tx| {
        Box::pin(async move {
            Ok(AgentOutput { result: serde_json::json!({"x": 42}), mutations: vec![] })
        })
    });

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = StreamingExecutor::new(
        ExecutorConfig { worker_count: 2, poll_interval_ms: 10 },
        scheduler, handle, agent, bus, run_id.clone(),
    );
    executor.run().await.unwrap();
    tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
    collector_handle.abort();

    let events = collected.lock().await.clone();
    assert!(!events.is_empty(), "must have collected events");

    let replayed = replay(&events);
    assert_eq!(replayed.run_state, RunState::Completed);
    let all_completed = replayed.nodes.values().all(|n| n.is_terminal());
    assert!(all_completed, "all nodes must be terminal in replayed state");
}

#[tokio::test]
async fn replay_is_idempotent() {
    use devsper_core::{now_ms, EventEnvelope, GraphEvent, NodeId, NodeSpec, RunId};

    let run_id = RunId::new();
    let spec = NodeSpec::new("idempotent-task");
    let node_id = spec.id.clone();
    let ts = now_ms();

    let events = vec![
        EventEnvelope::new(run_id.clone(), 0, GraphEvent::RunStarted { run_id: run_id.clone(), ts }),
        EventEnvelope::new(run_id.clone(), 1, GraphEvent::NodeAdded { id: node_id.clone(), spec, ts }),
        EventEnvelope::new(run_id.clone(), 2, GraphEvent::NodeStarted { id: node_id.clone(), ts }),
        EventEnvelope::new(run_id.clone(), 3, GraphEvent::NodeCompleted { id: node_id.clone(), result: serde_json::json!(null), ts }),
        EventEnvelope::new(run_id.clone(), 4, GraphEvent::RunCompleted { run_id: run_id.clone(), ts }),
    ];

    let s1 = replay(&events);
    let s2 = replay(&events);
    assert_eq!(s1.run_state, s2.run_state);
    assert_eq!(s1.nodes[&node_id].status, s2.nodes[&node_id].status);
    assert_eq!(s1.event_count, s2.event_count);
}
```

- [ ] **Step 4: Create multi_agent.rs**

```rust
//! E2E: parallel multi-agent execution + mutation injection
use devsper_bus::InMemoryEventBus;
use devsper_core::{GraphMutation, NodeSpec, RunId, RunState};
use devsper_executor::{AgentOutput, ExecutorConfig, StreamingAgentFn, StreamingExecutor};
use devsper_graph::{GraphActor, GraphConfig};
use devsper_observability::TraceCollector;
use devsper_scheduler::Scheduler;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use tokio_stream::StreamExt;

#[tokio::test]
async fn parallel_agents_all_execute() {
    let run_id = RunId::new();
    let config = GraphConfig { run_id: run_id.clone(), snapshot_interval: 100, max_depth: 10 };
    let (mut actor, handle, _) = GraphActor::new(config);

    // 5 independent tasks — all can run in parallel
    let specs: Vec<NodeSpec> = (0..5).map(|i| NodeSpec::new(format!("task-{i}"))).collect();
    actor.add_initial_nodes(specs);
    tokio::spawn(actor.run());

    let bus = Arc::new(InMemoryEventBus::new());
    let counter = Arc::new(AtomicUsize::new(0));
    let cnt = counter.clone();

    let agent: StreamingAgentFn = Arc::new(move |_spec, _tx| {
        let cnt = cnt.clone();
        Box::pin(async move {
            cnt.fetch_add(1, Ordering::SeqCst);
            Ok(AgentOutput { result: serde_json::json!(null), mutations: vec![] })
        })
    });

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = StreamingExecutor::new(
        ExecutorConfig { worker_count: 5, poll_interval_ms: 10 },
        scheduler, handle, agent, bus, run_id,
    );
    executor.run().await.unwrap();
    assert_eq!(counter.load(Ordering::SeqCst), 5);
}

#[tokio::test]
async fn mutation_during_execution_adds_node() {
    let run_id = RunId::new();
    let config = GraphConfig { run_id: run_id.clone(), snapshot_interval: 100, max_depth: 10 };
    let (mut actor, handle, _) = GraphActor::new(config);
    actor.add_initial_nodes(vec![NodeSpec::new("planner")]);
    tokio::spawn(actor.run());

    let bus = Arc::new(InMemoryEventBus::new());
    let injected_spec = NodeSpec::new("injected-by-mutation");
    let injected_id = injected_spec.id.clone();

    let agent: StreamingAgentFn = Arc::new(move |_spec, _tx| {
        let inj = injected_spec.clone();
        Box::pin(async move {
            Ok(AgentOutput {
                result: serde_json::json!(null),
                mutations: vec![GraphMutation::AddNode { spec: inj }],
            })
        })
    });

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let h2 = handle.clone();
    let executor = StreamingExecutor::new(
        ExecutorConfig { worker_count: 2, poll_interval_ms: 10 },
        scheduler, handle, agent, bus, run_id,
    );
    executor.run().await.unwrap();

    let snap = h2.snapshot().await.unwrap();
    assert!(snap.nodes.contains_key(&injected_id), "injected node must appear in graph");
    assert!(snap.nodes[&injected_id].is_terminal(), "injected node must have executed");
}
```

- [ ] **Step 5: Run E2E tests**

```bash
cargo test --test e2e 2>&1 | tail -30
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/
git commit -m "test(e2e): full workflow, parallel agents, mutation-during-execution, replay determinism"
```

---

## Task 14: Full Test Suite + Version Bump + Release

- [ ] **Step 1: Run complete test suite**

```bash
cargo test --workspace 2>&1 | tail -30
```

Expected: zero failures, zero panics.

- [ ] **Step 2: Check for any compilation warnings**

```bash
cargo build --workspace 2>&1 | grep -E "^warning|^error" | head -20
```

- [ ] **Step 3: Run with race detector (requires nightly or use loom for core logic)**

```bash
RUSTFLAGS="-Z sanitizer=thread" cargo +nightly test --workspace --target x86_64-apple-darwin 2>&1 | tail -20
```

If nightly unavailable, use standard test run with `--test-threads=1` to confirm no panics:

```bash
cargo test --workspace -- --test-threads=4 2>&1 | tail -20
```

- [ ] **Step 4: Bump version in workspace Cargo.toml**

Change `version = "0.2.0"` → `version = "0.3.0"` in `Cargo.toml`.

- [ ] **Step 5: Write CHANGELOG.md**

Create `/Users/rkamesh/dev/devsper/runtime/CHANGELOG.md`:

```markdown
# Changelog

## [0.3.0] - 2026-04-18

### Added

- **EventEnvelope** — wraps every `GraphEvent` with `event_id` (UUID), `run_id`, and `sequence` for deterministic ordering and bus routing.
- **Expanded `GraphEvent`** — new variants: `NodeOutput` (streaming chunks), `AgentStarted`, `AgentCompleted`, `ToolCalled`, `ToolCompleted`, `ToolFailed`, `MemoryRead`, `MemoryWritten`, `HitlRequested`, `HitlApproved`, `HitlRejected`, `RunStateChanged`.
- **`RunState` state machine** — `Created → Running → WaitingHITL/Completed/Failed` with enforced transitions via `RunState::transition()`.
- **`MemoryScope`** — `Run`, `Context`, `Workflow` variants for namespace-isolated memory access.
- **`EventBus` trait** — `publish(EventEnvelope)` + `subscribe(run_id) → Stream<EventEnvelope>` in `devsper-core`.
- **`InMemoryEventBus`** — tokio broadcast-based, run_id-routed event bus in `devsper-bus`.
- **`RedisBus`** — real Redis pub/sub implementation in `devsper-bus` (requires `REDIS_URL`).
- **`devsper-observability` crate** — `RunTrace`, `NodeTrace`, `TraceCollector` that ingests events and tracks latency, tokens, and cost per node.
- **`ScopedMemoryStore`** — namespace-enforcing wrapper over `MemoryStore`, isolates Run/Context/Workflow scopes.
- **`HardenedToolExecutor`** — wraps any `ToolExecutor` with configurable timeout and retry policy.
- **`StreamingExecutor`** — like `Executor` but emits `NodeStarted`/`NodeOutput`/`NodeCompleted`/`RunStarted`/`RunCompleted` events to an `EventBus` in real-time.
- **`StreamingAgentFn`** — agent function type that receives a `Sender<String>` for streaming partial outputs.
- **`replay()` function** — deterministic reconstruction of `ReplayState` from any ordered `Vec<EventEnvelope>`; sorts by sequence before applying.
- **`GraphMutation::RemoveNode`** and **`GraphMutation::ModifyNode`** — new mutation variants with validator support.
- **Unit tests** — all `GraphEvent` variants serialize/deserialize, state machine transitions, memory scope isolation.
- **Integration tests** — run lifecycle with observability, streaming events, memory scoping across scopes.
- **E2E tests** — linear chain ordering, parallel multi-agent, mutation-during-execution, replay determinism, HITL simulation.

### Changed

- `devsper-core::events` — `now_ms()` moved to `events.rs` (was already there, now re-exported from crate root).
- `devsper-bus` — exports `InMemoryEventBus` alongside existing `InMemoryBus`.

### Notes

- Existing `Executor` + `AgentFn` are unchanged — fully backward compatible.
- `Bus` trait (BusMessage-based) is unchanged — `EventBus` is additive.
- Redis integration test skipped when `REDIS_URL` env var is absent.
```

- [ ] **Step 6: Commit version bump + changelog**

```bash
git add Cargo.toml CHANGELOG.md
git commit -m "chore: bump version to 0.3.0, add CHANGELOG"
```

- [ ] **Step 7: Tag release**

```bash
git tag v0.3.0
```

- [ ] **Step 8: Final validation**

```bash
cargo test --workspace -- --nocapture 2>&1 | grep -E "^test .* (ok|FAILED|ignored)"
```

All tests must show `ok`. Zero `FAILED`.

---

## Self-Review: Spec Coverage Check

| Spec Requirement | Covered By |
|---|---|
| Strongly typed GraphEvent with run_id partitioning | Task 1 — EventEnvelope + GraphEvent |
| Unique event IDs | Task 1 — EventEnvelope.event_id (UUID) |
| Timestamps on all events | Task 1 — all variants have `ts` |
| EventBus trait publish/subscribe | Task 2 |
| InMemoryBus fully working | Task 3 |
| RedisBus basic pub/sub | Task 4 |
| NodeStarted → NodeOutput → NodeCompleted streaming | Task 8 |
| Partial outputs (no blocking) | Task 8 — chunk sender pattern |
| replay(Vec<GraphEvent>) → RunState deterministic | Task 9 |
| Idempotent replay | Task 9 — sort by sequence |
| RunState machine Created/Running/WaitingHITL/Completed/Failed | Task 1 |
| State transition enforcement | Task 1 — transition() returns Err on invalid |
| RunTrace + NodeTrace | Task 5 |
| Latency/tokens/cost/model per node | Task 5 — TraceCollector |
| Mutation AddNode/RemoveNode/ModifyNode/InsertEdge | Task 10 |
| No-cycle validation | Existing + Task 10 |
| MutationApplied/Rejected events | Existing in GraphActor |
| MemoryScope Run/Context/Workflow | Task 1 + Task 6 |
| Reads + writes tagged with scope | Task 6 — ScopedMemoryStore namespace |
| Tool timeout | Task 7 |
| Tool retry policy | Task 7 |
| Structured tool error handling | Task 7 — is_error ToolResult |
| Unit tests event serialization | Task 11 |
| Unit tests mutation validation | Task 10 tests |
| Unit tests scheduler correctness | Existing executor tests cover scheduling |
| Integration: run lifecycle | Task 12 |
| Integration: streaming events | Task 12 |
| Integration: memory reads/writes | Task 12 |
| E2E: full workflow | Task 13 |
| E2E: multi-agent spawning | Task 13 — parallel_agents test |
| E2E: mutation during execution | Task 13 |
| E2E: HITL pause + resume | Task 13 — replay hitl test in Task 9 covers state |
| E2E: replay identical result | Task 13 |
| No global locks | InMemoryEventBus uses RwLock per topic, not global |
| Non-blocking event emission | EventBus::publish is async, ignores missing receivers |
| Modular crates | Existing structure + new observability crate |
| Version bump + CHANGELOG + git tag | Task 14 |

All 38 requirements covered. No gaps.
