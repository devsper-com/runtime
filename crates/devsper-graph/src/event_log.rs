use devsper_core::{GraphEvent, GraphSnapshot};

/// Append-only log of all graph events.
/// Snapshots every N events for efficient recovery without full replay.
pub struct EventLog {
    events: Vec<GraphEvent>,
    snapshot_interval: u64,
    last_snapshot: Option<GraphSnapshot>,
    last_snapshot_at: u64,
}

impl EventLog {
    pub fn new(snapshot_interval: u64) -> Self {
        Self {
            events: Vec::new(),
            snapshot_interval,
            last_snapshot: None,
            last_snapshot_at: 0,
        }
    }

    pub fn append(&mut self, event: GraphEvent) {
        self.events.push(event);
    }

    pub fn events(&self) -> &[GraphEvent] {
        &self.events
    }

    pub fn len(&self) -> usize {
        self.events.len()
    }

    pub fn is_empty(&self) -> bool {
        self.events.is_empty()
    }

    pub fn record_snapshot(&mut self, snapshot: GraphSnapshot) {
        self.last_snapshot_at = self.events.len() as u64;
        self.last_snapshot = Some(snapshot);
    }

    pub fn should_snapshot(&self) -> bool {
        self.snapshot_interval > 0
            && (self.events.len() as u64).saturating_sub(self.last_snapshot_at)
                >= self.snapshot_interval
    }

    pub fn last_snapshot(&self) -> Option<&GraphSnapshot> {
        self.last_snapshot.as_ref()
    }

    /// Events since last snapshot (for replay from snapshot)
    pub fn events_since_snapshot(&self) -> &[GraphEvent] {
        let start = self.last_snapshot_at as usize;
        if start < self.events.len() {
            &self.events[start..]
        } else {
            &[]
        }
    }
}
