//! Task type compatible with Python Task (to_dict/from_dict).

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum TaskStatus {
    #[default]
    Pending = 0,
    Running = 1,
    Completed = 2,
    Failed = -1,
}

impl TaskStatus {
    pub fn from_i64(v: i64) -> Self {
        match v {
            0 => TaskStatus::Pending,
            1 => TaskStatus::Running,
            2 => TaskStatus::Completed,
            -1 => TaskStatus::Failed,
            _ => TaskStatus::Pending,
        }
    }
}

impl serde::Serialize for TaskStatus {
    fn serialize<S>(&self, serializer: S) -> std::result::Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_i64(*self as i64)
    }
}

impl<'de> serde::Deserialize<'de> for TaskStatus {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        let v = i64::deserialize(deserializer)?;
        Ok(Self::from_i64(v))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    pub id: String,
    pub description: String,
    #[serde(default)]
    pub dependencies: Vec<String>,
    #[serde(default)]
    pub status: TaskStatus,
    pub result: Option<String>,
    pub error: Option<String>,
    #[serde(default)]
    pub speculative: bool,
    pub role: Option<String>,
    #[serde(default)]
    pub retry_count: u32,
}

impl Task {
    pub fn status_value(&self) -> i64 {
        self.status as i64
    }
}
