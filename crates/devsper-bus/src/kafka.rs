/// Kafka bus backend (stub — full implementation in Phase 8 cluster).
pub struct KafkaBus;

impl KafkaBus {
    pub fn new(_brokers: &[String], _group_id: &str) -> Self {
        Self
    }
}
