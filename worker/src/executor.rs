//! Bridge to Python agent execution: subprocess (default) or PyO3.

use std::process::Stdio;
use std::time::Duration;

use tokio::io::{AsyncBufReadExt, AsyncReadExt, BufReader};
use tokio::process::Command;

use crate::error::{DevsperError, Result};
use crate::types::{AgentRequest, AgentResponse};

const DEFAULT_TASK_TIMEOUT_SECS: u64 = 300;

/// Execute agent via Python subprocess: stdin JSON request, stdout JSON response.
#[cfg(feature = "subprocess-executor")]
pub async fn run_agent_subprocess(
    python_bin: &str,
    request: &AgentRequest,
    timeout_secs: Option<u64>,
) -> Result<AgentResponse> {
    let json_in = serde_json::to_string(request).map_err(DevsperError::Json)?;
    let timeout = timeout_secs.unwrap_or(DEFAULT_TASK_TIMEOUT_SECS);
    let mut child = Command::new(python_bin)
        .args(["-m", "devsper.agents.run_agent"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| DevsperError::Executor(format!("spawn: {}", e)))?;
    if let Some(mut stdin) = child.stdin.take() {
        use tokio::io::AsyncWriteExt;
        stdin
            .write_all(json_in.as_bytes())
            .await
            .map_err(|e| DevsperError::Executor(format!("stdin: {}", e)))?;
        stdin
            .write_all(b"\n")
            .await
            .map_err(|e| DevsperError::Executor(format!("stdin: {}", e)))?;
        stdin
            .shutdown()
            .await
            .map_err(|e| DevsperError::Executor(format!("stdin shutdown: {}", e)))?;
    }
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| DevsperError::Executor("no stdout".to_string()))?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| DevsperError::Executor("no stderr".to_string()))?;
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();
    let read_fut = reader.read_line(&mut line);
    let timeout_fut = tokio::time::sleep(Duration::from_secs(timeout));
    tokio::select! {
        _ = timeout_fut => {
            let _ = child.start_kill();
            return Err(DevsperError::Timeout(format!("task timeout after {}s", timeout)));
        }
        r = read_fut => {
            r.map_err(|e| DevsperError::Executor(format!("read stdout: {}", e)))?;
        }
    }
    let status = child.wait().await;
    if line.is_empty() {
        let mut err_out = String::new();
        let _ = AsyncReadExt::read_to_string(&mut BufReader::new(stderr), &mut err_out).await;
        let hint = if err_out.contains("ModuleNotFoundError") || err_out.contains("No module named") {
            " (is DEVSPER_PYTHON_BIN set to your venv python? e.g. .venv/bin/python)"
        } else {
            ""
        };
        tracing::warn!("agent stderr: {}", err_out.trim().lines().next().unwrap_or(""));
        return Err(DevsperError::InvalidPayload(format!(
            "empty response from agent{}. Exit: {:?}",
            hint,
            status.ok().and_then(|s| s.code())
        )));
    }
    let response: AgentResponse = serde_json::from_str(line.trim())
        .map_err(|e| DevsperError::InvalidPayload(format!("agent response JSON: {}", e)))?;
    Ok(response)
}

/// Placeholder when not using subprocess (e.g. PyO3 only build).
#[cfg(not(feature = "subprocess-executor"))]
pub async fn run_agent_subprocess(
    _python_bin: &str,
    _request: &AgentRequest,
    _timeout_secs: Option<u64>,
) -> Result<AgentResponse> {
    Err(DevsperError::Executor(
        "subprocess executor not enabled".to_string(),
    ))
}

#[cfg(feature = "pyo3-executor")]
pub async fn run_agent_pyo3(
    request: &AgentRequest,
    _timeout_secs: Option<u64>,
) -> Result<AgentResponse> {
    let json_in = serde_json::to_string(request).map_err(DevsperError::Json)?;
    let json_out = pyo3::Python::with_gil(|py| {
        let run_agent = py
            .import("devsper.agents.run_agent")?
            .getattr("run_agent_sync")?;
        let out: &pyo3::types::PyString = run_agent.call1((json_in,))?.extract()?;
        Ok::<String, pyo3::PyErr>(out.to_string())
    })
    .map_err(|e| DevsperError::Executor(format!("pyo3: {}", e)))?;
    let response: AgentResponse = serde_json::from_str(&json_out)
        .map_err(|e| DevsperError::InvalidPayload(format!("agent response: {}", e)))?;
    Ok(response)
}

#[cfg(not(feature = "pyo3-executor"))]
pub async fn run_agent_pyo3(
    _request: &AgentRequest,
    _timeout_secs: Option<u64>,
) -> Result<AgentResponse> {
    Err(DevsperError::Executor(
        "pyo3 executor not enabled".to_string(),
    ))
}
