//! Axum HTTP server: /health, /status, /tasks, /control, /stream/events.

use axum::{
    extract::State,
    http::StatusCode,
    response::sse::{Event, Sse},
    routing::{get, post},
    Json, Router,
};
use std::sync::Arc;
use std::time::Instant;
use tower_http::cors::CorsLayer;

const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Type alias for optional async status getter (used by controller).
pub type GetStatusFn = Arc<
    std::sync::Mutex<
        Option<
            Arc<
                dyn Fn() -> std::pin::Pin<
                        Box<dyn std::future::Future<Output = serde_json::Value> + Send>,
                    > + Send
                    + Sync,
            >,
        >,
    >,
>;

pub struct RpcState {
    pub node_id: String,
    pub role: String,
    pub started_at: Instant,
    pub get_status: GetStatusFn,
    pub get_current_tasks: Arc<dyn Fn() -> Vec<serde_json::Value> + Send + Sync>,
    pub rpc_token: Option<String>,
}

pub fn app(state: Arc<RpcState>) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/status", get(status))
        .route("/tasks", get(tasks))
        .route("/control", post(control))
        .route("/stream/events", get(stream_events))
        .layer(CorsLayer::permissive())
        .with_state(state)
}

async fn health(State(s): State<Arc<RpcState>>) -> Json<serde_json::Value> {
    Json(serde_json::json!({
        "node_id": s.node_id,
        "role": s.role,
        "healthy": true,
        "uptime_seconds": s.started_at.elapsed().as_secs_f64(),
        "version": VERSION,
    }))
}

async fn status(State(s): State<Arc<RpcState>>) -> Json<serde_json::Value> {
    let f = s.get_status.lock().unwrap().clone();
    let status = match f.as_ref() {
        Some(f) => f().await,
        None => serde_json::json!({}),
    };
    Json(status)
}

async fn tasks(State(s): State<Arc<RpcState>>) -> Json<Vec<serde_json::Value>> {
    Json((s.get_current_tasks)())
}

async fn control(
    State(s): State<Arc<RpcState>>,
    headers: axum::http::HeaderMap,
    Json(body): Json<serde_json::Value>,
) -> (StatusCode, Json<serde_json::Value>) {
    if let Some(ref token) = s.rpc_token {
        let auth = headers
            .get("x-devsper-token")
            .or_else(|| headers.get("authorization"));
        let valid = auth
            .and_then(|v| v.to_str().ok())
            .map(|v| v.strip_prefix("Bearer ").unwrap_or(v) == token.as_str())
            .unwrap_or(false);
        if !valid {
            return (
                StatusCode::UNAUTHORIZED,
                Json(serde_json::json!({"error": "Invalid or missing token"})),
            );
        }
    }
    let _ = body.get("command").and_then(|v| v.as_str());
    let _ = body.get("target").and_then(|v| v.as_str());
    (StatusCode::OK, Json(serde_json::json!({"ok": true})))
}

async fn stream_events(
) -> Sse<impl futures::Stream<Item = std::result::Result<Event, std::io::Error>> + Send + 'static> {
    let stream = futures::stream::unfold((), |_| {
        Box::pin(async move {
            tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
            let data = serde_json::json!({"t": "ping"}).to_string();
            Some((Ok(Event::default().data(data)), ()))
        })
    });
    Sse::new(stream)
}
