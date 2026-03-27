//! devsper worker node — bus, claim protocol, heartbeat, executor bridge.

pub mod bus;
pub mod budget;
pub mod claim;
pub mod clarification;
pub mod config;
pub mod controller;
pub mod election;
pub mod error;
pub mod executor;
pub mod health;
pub mod heartbeat;
pub mod metrics;
pub mod reconnect;
pub mod registry;
pub mod router;
pub mod rpc;
pub mod scheduler;
pub mod snapshot;
pub mod telemetry;
pub mod types;
pub mod worker_node;

pub use config::{ExecutorMode, NodeConfig};
pub use error::{DevsperError, Result};
pub use types::{AgentRequest, AgentResponse, BusMessage, NodeInfo, NodeRole, Task, TaskStatus};
