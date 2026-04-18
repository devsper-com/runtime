pub mod event_bus;
pub mod kafka;
pub mod memory;
pub mod redis;

pub use event_bus::InMemoryEventBus;
pub use memory::InMemoryBus;

use devsper_core::Bus;
use std::sync::Arc;

/// Create a bus from a config string.
/// "memory"      → InMemoryBus
/// "redis://..."  → stub (returns error until Phase 8)
/// "kafka://..."  → stub
pub fn create_bus(_config: &str) -> Arc<dyn Bus> {
    Arc::new(InMemoryBus::new())
}
