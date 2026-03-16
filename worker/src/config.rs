//! Node configuration from environment and optional TOML (12-factor).

use std::env;

use crate::error::{DevsperError, Result};
use crate::types::NodeRole;

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}

fn env_u32(key: &str, default: u32) -> u32 {
    env::var(key)
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(default)
}

fn env_u16(key: &str, default: u16) -> u16 {
    env::var(key)
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(default)
}

#[derive(Debug, Clone)]
pub struct NodeConfig {
    pub node_role: NodeRole,
    pub node_id: String,
    pub node_tags: Vec<String>,
    pub max_workers: u32,
    pub rpc_port: u16,
    pub rpc_token: Option<String>,
    pub redis_url: String,
    pub run_id: String,
    pub heartbeat_interval_secs: u64,
    pub claim_timeout_secs: u64,
    pub log_level: String,
    pub log_format: String,
    pub python_bin: String,
    pub executor_mode: ExecutorMode,
    /// Model for agent execution (e.g. "mock", "github:gpt-4o"). Passed in AgentRequest.
    pub worker_model: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutorMode {
    Subprocess,
    PyO3,
}

impl std::str::FromStr for ExecutorMode {
    type Err = DevsperError;
    fn from_str(s: &str) -> Result<Self> {
        match s.to_lowercase().as_str() {
            "subprocess" => Ok(ExecutorMode::Subprocess),
            "pyo3" => Ok(ExecutorMode::PyO3),
            _ => Err(DevsperError::Config(format!(
                "Unknown executor mode: {}",
                s
            ))),
        }
    }
}

impl NodeConfig {
    pub fn from_env() -> Result<Self> {
        let role_str = env_or("DEVSPER_NODE_ROLE", "hybrid");
        let node_role = match role_str.to_lowercase().as_str() {
            "controller" => NodeRole::Controller,
            "worker" => NodeRole::Worker,
            "hybrid" => NodeRole::Hybrid,
            _ => NodeRole::Hybrid,
        };

        let node_id = env_or("DEVSPER_NODE_ID", "");
        let node_id = if node_id.is_empty() {
            uuid::Uuid::new_v4().to_string()
        } else {
            node_id
        };

        let tags_str = env_or("DEVSPER_NODE_TAGS", "");
        let node_tags = if tags_str.is_empty() {
            vec![]
        } else {
            tags_str
                .split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect()
        };

        let run_id = env_or("DEVSPER_RUN_ID", "");
        if run_id.is_empty() {
            return Err(DevsperError::Config(
                "DEVSPER_RUN_ID is required".to_string(),
            ));
        }

        let executor_str = env_or("DEVSPER_EXECUTOR_MODE", "subprocess");
        let executor_mode = executor_str.parse()?;

        Ok(Self {
            node_role,
            node_id,
            node_tags,
            max_workers: env_u32("DEVSPER_MAX_WORKERS", 4),
            rpc_port: env_u16("DEVSPER_RPC_PORT", 7700),
            rpc_token: env::var("DEVSPER_RPC_TOKEN").ok(),
            redis_url: env_or("DEVSPER_REDIS_URL", "redis://localhost:6379"),
            run_id,
            heartbeat_interval_secs: env_u32("DEVSPER_HEARTBEAT_INTERVAL", 10) as u64,
            claim_timeout_secs: env_u32("DEVSPER_CLAIM_TIMEOUT", 30) as u64,
            log_level: env_or("DEVSPER_LOG_LEVEL", "info"),
            log_format: env_or("DEVSPER_LOG_FORMAT", "text"),
            python_bin: env_or("DEVSPER_PYTHON_BIN", "python3"),
            executor_mode,
            worker_model: env_or("DEVSPER_WORKER_MODEL", "mock"),
        })
    }
}
