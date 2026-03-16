//! Error types for devsper-worker.

use thiserror::Error;

#[derive(Error, Debug)]
pub enum DevsperError {
    #[error("Redis: {0}")]
    Redis(#[from] redis::RedisError),

    #[error("IO: {0}")]
    Io(#[from] std::io::Error),

    #[error("JSON: {0}")]
    Json(#[from] serde_json::Error),

    #[error("Bus connection: {0}")]
    BusConnection(String),

    #[error("Config: {0}")]
    Config(String),

    #[error("Executor: {0}")]
    Executor(String),

    #[error("Timeout: {0}")]
    Timeout(String),

    #[error("Invalid payload: {0}")]
    InvalidPayload(String),
}

pub type Result<T> = std::result::Result<T, DevsperError>;
