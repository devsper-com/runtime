//! Minimal scheduler for controller: restore from snapshot, ready tasks, mark completed/failed.

use std::collections::HashMap;

use crate::types::{Task, TaskStatus};

/// In-memory task DAG for controller; mirrors Python Scheduler snapshot shape.
#[derive(Default)]
pub struct Scheduler {
    pub run_id: String,
    tasks: HashMap<String, Task>,
    edges: Vec<(String, String)>,
}

impl Scheduler {
    pub fn new(run_id: String) -> Self {
        Self {
            run_id,
            tasks: HashMap::new(),
            edges: Vec::new(),
        }
    }

    pub fn add_tasks(&mut self, tasks: Vec<Task>) {
        for t in tasks {
            self.tasks.insert(t.id.clone(), t);
        }
        // Edges must be set separately or from snapshot
    }

    pub fn get_ready_tasks(&self) -> Vec<Task> {
        let mut ready = Vec::new();
        for (id, task) in &self.tasks {
            if task.status != TaskStatus::Pending {
                continue;
            }
            let deps: Vec<&String> = self
                .edges
                .iter()
                .filter(|(_, v)| v == id)
                .map(|(u, _)| u)
                .collect();
            let all_done = deps
                .iter()
                .filter_map(|d| self.tasks.get(*d))
                .all(|t| t.status == TaskStatus::Completed);
            if all_done {
                ready.push(task.clone());
            }
        }
        ready
    }

    pub fn mark_completed(&mut self, task_id: &str, result: &str) {
        if let Some(t) = self.tasks.get_mut(task_id) {
            t.status = TaskStatus::Completed;
            t.result = Some(result.to_string());
        }
    }

    pub fn mark_failed(&mut self, task_id: &str, error: &str) {
        if let Some(t) = self.tasks.get_mut(task_id) {
            t.status = TaskStatus::Failed;
            t.error = Some(error.to_string());
        }
    }

    pub fn is_finished(&self) -> bool {
        self.tasks
            .values()
            .all(|t| t.status == TaskStatus::Completed || t.status == TaskStatus::Failed)
    }

    pub fn snapshot(&self) -> serde_json::Value {
        let tasks_data: Vec<serde_json::Value> = self
            .tasks
            .values()
            .map(|t| serde_json::to_value(t).unwrap_or_default())
            .collect();
        let edges_data: Vec<Vec<String>> = self
            .edges
            .iter()
            .map(|(u, v)| vec![u.clone(), v.clone()])
            .collect();
        let completed_count = self
            .tasks
            .values()
            .filter(|t| t.status == TaskStatus::Completed)
            .count();
        let failed_count = self
            .tasks
            .values()
            .filter(|t| t.status == TaskStatus::Failed)
            .count();
        serde_json::json!({
            "run_id": self.run_id,
            "tasks": tasks_data,
            "edges": edges_data,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "snapshot_at": chrono::Utc::now().to_rfc3339(),
        })
    }

    pub fn restore(snapshot: &serde_json::Value) -> Option<Self> {
        let run_id = snapshot.get("run_id")?.as_str()?.to_string();
        let tasks_data = snapshot.get("tasks")?.as_array()?;
        let mut tasks = HashMap::new();
        for t in tasks_data {
            let task: Task = serde_json::from_value(t.clone()).ok()?;
            tasks.insert(task.id.clone(), task);
        }
        let edges_data = snapshot.get("edges")?.as_array()?;
        let mut edges = Vec::new();
        for e in edges_data {
            let pair = e.as_array()?;
            if pair.len() >= 2 {
                let u = pair[0].as_str()?.to_string();
                let v = pair[1].as_str()?.to_string();
                edges.push((u, v));
            }
        }
        Some(Self {
            run_id,
            tasks,
            edges,
        })
    }

    pub fn get_all_tasks(&self) -> Vec<&Task> {
        self.tasks.values().collect()
    }
}
