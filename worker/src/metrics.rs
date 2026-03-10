//! Internal counters — tasks completed, latency, errors.

use std::sync::atomic::{AtomicU64, Ordering};

pub struct Metrics {
    pub tasks_completed: AtomicU64,
    pub tasks_failed: AtomicU64,
    pub errors: AtomicU64,
}

impl Default for Metrics {
    fn default() -> Self {
        Self {
            tasks_completed: AtomicU64::new(0),
            tasks_failed: AtomicU64::new(0),
            errors: AtomicU64::new(0),
        }
    }
}

impl Metrics {
    pub fn inc_completed(&self) {
        self.tasks_completed.fetch_add(1, Ordering::Relaxed);
    }
    pub fn inc_failed(&self) {
        self.tasks_failed.fetch_add(1, Ordering::Relaxed);
    }
    pub fn inc_errors(&self) {
        self.errors.fetch_add(1, Ordering::Relaxed);
    }
}
