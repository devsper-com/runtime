# devsper-cluster

Peer-to-peer cluster coordination for the devsper distributed runtime. Implements a lightweight gossip/heartbeat protocol so worker nodes can discover each other, elect a coordinator, and track liveness.

## Roles

| Role | Responsibility |
|------|---------------|
| `Coordinator` | Accepts new runs, assigns tasks to workers, tracks global budget |
| `Worker` | Polls the scheduler, executes tasks, reports results |
| `Candidate` | Transitional state during leader election |

## Protocol

Nodes communicate via `ClusterMessage` envelopes over the bus:

- **Heartbeat** — periodic liveness signal; missing beats mark peers dead
- **TaskAssign** — coordinator → worker: claim this node
- **TaskResult** — worker → coordinator: result + metrics
- **PeerJoin / PeerLeave** — membership changes

## Usage

```toml
[dependencies]
devsper-cluster = "0.1"
```

```rust
use devsper_cluster::{ClusterConfig, ClusterNode};

let config = ClusterConfig {
    node_id: "node-1".into(),
    listen_address: "0.0.0.0:7000".into(),
    known_peers: vec!["10.0.0.2:7000".into()],
    heartbeat_interval_ms: 1000,
    heartbeat_timeout_ms: 5000,
};

let node = ClusterNode::new(config);
node.start().await?;
```

## Worker registry

`WorkerRegistry` tracks all live peers and their capabilities. The coordinator uses it to route tasks to the best available worker.

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
