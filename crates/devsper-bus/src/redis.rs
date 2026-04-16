/// Redis bus backend (stub — full implementation in Phase 8 cluster).
/// Currently returns an error to make the feature boundary clear.
pub struct RedisBus;

impl RedisBus {
    pub fn new(_url: &str) -> Self {
        Self
    }
}
