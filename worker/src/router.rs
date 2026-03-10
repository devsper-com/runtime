//! Task routing — memory affinity, tool affinity, load score.

use std::collections::HashMap;

use crate::types::{NodeInfo, Task};

fn parse_version(version: &str) -> (u32, u32) {
    let binding = version.replace('-', ".");
    let parts: Vec<&str> = binding.split('.').collect();
    let major = parts.first().and_then(|s| s.parse().ok()).unwrap_or(0);
    let minor = parts.get(1).and_then(|s| s.parse().ok()).unwrap_or(0);
    (major, minor)
}

fn clamp(value: f64, lo: f64, hi: f64) -> f64 {
    value.max(lo).min(hi)
}

/// Route ready task to best worker. Scoring: memory_affinity, tool_affinity, load_score.
pub struct TaskRouter {
    controller_version: String,
    round_robin_index: usize,
}

impl TaskRouter {
    pub const MEMORY_WEIGHT: f64 = 0.35;
    pub const TOOL_WEIGHT: f64 = 0.25;
    pub const LOAD_WEIGHT: f64 = 0.40;

    pub fn new(controller_version: impl Into<String>) -> Self {
        Self {
            controller_version: controller_version.into(),
            round_robin_index: 0,
        }
    }

    pub fn route<'a>(
        &mut self,
        task: &Task,
        workers: &'a [NodeInfo],
        worker_stats: &HashMap<String, serde_json::Value>,
    ) -> Option<&'a NodeInfo> {
        if workers.is_empty() {
            return None;
        }
        let (ctrl_major, ctrl_minor) = parse_version(&self.controller_version);
        let eligible: Vec<&'a NodeInfo> = workers
            .iter()
            .filter(|w| {
                let (maj, min) = parse_version(&w.version);
                maj == ctrl_major && min == ctrl_minor
            })
            .collect();
        if eligible.is_empty() {
            return None;
        }
        let empty = serde_json::Map::new();
        let scored: Vec<(f64, &'a NodeInfo)> = eligible
            .iter()
            .map(|w| {
                let stats = worker_stats
                    .get(&w.node_id)
                    .and_then(|v| v.as_object())
                    .unwrap_or(&empty);
                let score = self.score(task, w, stats);
                (score, *w)
            })
            .collect();
        let best = scored.iter().map(|(s, _)| *s).fold(0.0_f64, f64::max);
        if best < 0.0 {
            return None;
        }
        let eps = 1e-6;
        let tied: Vec<&'a NodeInfo> = scored
            .iter()
            .filter(|(s, _)| (s - best).abs() <= eps)
            .map(|(_, w)| *w)
            .collect();
        let idx = self.round_robin_index % tied.len();
        self.round_robin_index += 1;
        Some(tied[idx])
    }

    fn score(
        &self,
        task: &Task,
        worker: &NodeInfo,
        stats: &serde_json::Map<String, serde_json::Value>,
    ) -> f64 {
        let memory = memory_affinity(task, stats);
        let tool = tool_affinity(task, stats);
        let load = load_score(worker, stats);
        memory * Self::MEMORY_WEIGHT + tool * Self::TOOL_WEIGHT + load * Self::LOAD_WEIGHT
    }
}

fn memory_affinity(task: &Task, stats: &serde_json::Map<String, serde_json::Value>) -> f64 {
    let deps = &task.dependencies;
    if deps.is_empty() {
        return 0.0;
    }
    let completed: Vec<String> = stats
        .get("completed_task_ids")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    let hit = deps.iter().filter(|d| completed.contains(d)).count();
    hit as f64 / deps.len() as f64
}

fn tool_affinity(_task: &Task, stats: &serde_json::Map<String, serde_json::Value>) -> f64 {
    let cached: Vec<String> = stats
        .get("cached_tools")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    if cached.is_empty() {
        return 0.0;
    }
    // Rust worker doesn't have Python tool selector; use 0 or 1.0 to not penalize
    0.0
}

fn load_score(worker: &NodeInfo, stats: &serde_json::Map<String, serde_json::Value>) -> f64 {
    let active = stats
        .get("active_tasks")
        .and_then(|v| v.as_u64())
        .unwrap_or(0) as f64;
    let avg_duration = stats
        .get("avg_task_duration_seconds")
        .and_then(|v| v.as_f64())
        .unwrap_or(0.0);
    let max_workers = worker.max_workers as f64;
    let weighted_load = active * avg_duration;
    let load_ratio = weighted_load / (max_workers * 60.0).max(1.0);
    1.0 - clamp(load_ratio, 0.0, 1.0)
}
