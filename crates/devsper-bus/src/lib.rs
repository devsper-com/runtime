pub mod event_bus;
pub mod kafka;
pub mod memory;
pub mod redis;

pub use event_bus::InMemoryEventBus;
pub use kafka::KafkaBus;
pub use memory::InMemoryBus;
pub use redis::RedisBus;

use devsper_core::Bus;
use std::sync::Arc;

pub fn create_bus(_config: &str) -> Arc<dyn Bus> {
    Arc::new(InMemoryBus::new())
}
