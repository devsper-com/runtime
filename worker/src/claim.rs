//! Task claim protocol — publish claim, await grant/reject with timeout.

use tokio::sync::oneshot;

use crate::error::Result;
use crate::types::event::topics;
use crate::types::{BusMessage, Task};

/// Claim state for one task: we published TASK_CLAIMED, waiting for TASK_CLAIM_GRANTED or TASK_CLAIM_REJECTED or timeout.
pub struct ClaimWaiter {
    pub task_id: String,
    pub worker_id: String,
    pub grant_tx: Option<oneshot::Sender<bool>>,
}

/// Create a BusMessage for TASK_CLAIMED.
pub fn make_claim_message(
    task_id: &str,
    worker_id: &str,
    run_id: &str,
    sender_id: &str,
) -> BusMessage {
    BusMessage {
        id: uuid::Uuid::new_v4().to_string(),
        topic: topics::TASK_CLAIMED.to_string(),
        payload: serde_json::json!({
            "task_id": task_id,
            "worker_id": worker_id,
        }),
        sender_id: sender_id.to_string(),
        timestamp: chrono::Utc::now().to_rfc3339(),
        run_id: run_id.to_string(),
        schema_version: None,
    }
}

/// Create a BusMessage for TASK_READY (controller dispatches task).
pub fn make_task_ready_message(
    task: &Task,
    target_worker_id: &str,
    run_id: &str,
    sender_id: &str,
) -> Result<BusMessage> {
    let payload = serde_json::json!({
        "id": task.id,
        "description": task.description,
        "dependencies": task.dependencies,
        "status": task.status_value(),
        "result": task.result,
        "error": task.error,
        "speculative": task.speculative,
        "role": task.role,
        "retry_count": task.retry_count,
        "target_worker_id": target_worker_id,
    });
    Ok(BusMessage {
        id: uuid::Uuid::new_v4().to_string(),
        topic: topics::TASK_READY.to_string(),
        payload,
        sender_id: sender_id.to_string(),
        timestamp: chrono::Utc::now().to_rfc3339(),
        run_id: run_id.to_string(),
        schema_version: None,
    })
}
