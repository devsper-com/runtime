//! Reconnect policy — exponential backoff, re-register on recovery.

use std::time::Duration;

/// Exponential backoff for reconnection attempts.
pub struct ReconnectPolicy {
    pub initial_delay_secs: u64,
    pub max_delay_secs: u64,
    pub multiplier: f64,
    attempt: u32,
}

impl Default for ReconnectPolicy {
    fn default() -> Self {
        Self {
            initial_delay_secs: 1,
            max_delay_secs: 60,
            multiplier: 2.0,
            attempt: 0,
        }
    }
}

impl ReconnectPolicy {
    pub fn next_delay(&mut self) -> Duration {
        let delay_secs = (self.initial_delay_secs as f64
            * self.multiplier.powi(self.attempt as i32))
        .min(self.max_delay_secs as f64) as u64;
        self.attempt += 1;
        Duration::from_secs(delay_secs)
    }

    pub fn reset(&mut self) {
        self.attempt = 0;
    }
}
