use anyhow::Result;
use async_trait::async_trait;
use devsper_core::{ToolCall, ToolDef, ToolExecutor, ToolResult};
use std::sync::Arc;
use tokio::time::{timeout, Duration};
use tracing::warn;

#[derive(Debug, Clone)]
pub struct ToolPolicy {
    pub timeout_ms: u64,
    pub max_retries: u32,
    pub retry_delay_ms: u64,
}

impl Default for ToolPolicy {
    fn default() -> Self {
        Self {
            timeout_ms: 10_000,
            max_retries: 2,
            retry_delay_ms: 200,
        }
    }
}

pub struct HardenedToolExecutor {
    inner: Arc<dyn ToolExecutor>,
    policy: ToolPolicy,
}

impl HardenedToolExecutor {
    pub fn new(inner: Arc<dyn ToolExecutor>, policy: ToolPolicy) -> Self {
        Self { inner, policy }
    }
}

#[async_trait]
impl ToolExecutor for HardenedToolExecutor {
    async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
        let mut last_err = anyhow::anyhow!("no attempts made");
        for attempt in 0..=self.policy.max_retries {
            if attempt > 0 {
                tokio::time::sleep(Duration::from_millis(self.policy.retry_delay_ms)).await;
                warn!(tool = %call.name, attempt, "retrying tool call");
            }
            let fut = self.inner.execute(call.clone());
            match timeout(Duration::from_millis(self.policy.timeout_ms), fut).await {
                Ok(Ok(result)) => return Ok(result),
                Ok(Err(e)) => last_err = e,
                Err(_) => {
                    last_err = anyhow::anyhow!(
                        "tool '{}' timed out after {}ms",
                        call.name,
                        self.policy.timeout_ms
                    );
                }
            }
        }
        Ok(ToolResult {
            tool_call_id: call.id,
            content: serde_json::json!({ "error": last_err.to_string() }),
            is_error: true,
        })
    }

    fn list_tools(&self) -> Vec<ToolDef> {
        self.inner.list_tools()
    }
}

// ---------------------------------------------------------------------------
// Standard tool stubs
// ---------------------------------------------------------------------------
// These tools define schemas that the LLM can use. The actual API calls are
// delegated to the Go integration service via HTTP. Each tool's execute fn
// either calls back to the platform or returns a stub response when the
// platform URL is not configured.

/// Configuration for the platform callback endpoint that standard tools use.
#[derive(Debug, Clone)]
pub struct PlatformCallbackConfig {
    /// Base URL of the platform API, e.g. "http://localhost:8080/api/v1".
    pub platform_url: String,
    /// Optional internal secret for authenticating callback requests.
    pub internal_secret: Option<String>,
}

impl Default for PlatformCallbackConfig {
    fn default() -> Self {
        Self {
            platform_url: String::new(),
            internal_secret: None,
        }
    }
}

/// StandardTools provides built-in tool definitions that route execution to
/// the Go integration service via HTTP callbacks.
pub struct StandardTools {
    callback: PlatformCallbackConfig,
    http: reqwest::Client,
}

impl StandardTools {
    pub fn new(callback: PlatformCallbackConfig) -> Self {
        Self {
            callback,
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .unwrap_or_default(),
        }
    }

    /// Returns the tool definitions for all standard tools.
    pub fn tool_definitions() -> Vec<ToolDef> {
        vec![
            ToolDef {
                name: "http_request".into(),
                description: "Make an HTTP request with automatic auth injection. \
                    Supports GET, POST, PUT, PATCH, DELETE methods. \
                    The platform injects OAuth tokens or API keys based on the target service."
                    .into(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                            "description": "HTTP method"
                        },
                        "url": {
                            "type": "string",
                            "description": "Target URL"
                        },
                        "headers": {
                            "type": "object",
                            "description": "Optional request headers",
                            "additionalProperties": { "type": "string" }
                        },
                        "body": {
                            "description": "Optional request body (JSON string or object)"
                        },
                        "service": {
                            "type": "string",
                            "enum": ["github", "slack", "stripe", "notion", "linear", "generic"],
                            "description": "Service for auth injection. 'generic' sends no auth.",
                            "default": "generic"
                        }
                    },
                    "required": ["method", "url"]
                }),
            },
            ToolDef {
                name: "file_read".into(),
                description:
                    "Read a file from blob storage. Returns the file content as a string. \
                    Uses pre-signed download URLs generated by the platform storage service."
                        .into(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "object_key": {
                            "type": "string",
                            "description": "Storage object key (returned by file_write or upload)"
                        },
                        "org_id": {
                            "type": "string",
                            "description": "Organization ID that owns the file"
                        },
                        "encoding": {
                            "type": "string",
                            "enum": ["utf-8", "base64", "raw"],
                            "description": "File encoding. Use base64 for binary files.",
                            "default": "utf-8"
                        }
                    },
                    "required": ["object_key", "org_id"]
                }),
            },
            ToolDef {
                name: "file_write".into(),
                description: "Write a file to blob storage. Returns the object key for later \
                    retrieval. Supports text and binary (base64) content."
                    .into(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Filename with extension (e.g. 'report.md')"
                        },
                        "content": {
                            "type": "string",
                            "description": "File content. For binary, provide base64-encoded data."
                        },
                        "org_id": {
                            "type": "string",
                            "description": "Organization ID for the file"
                        },
                        "content_type": {
                            "type": "string",
                            "description": "MIME type (e.g. 'text/markdown', 'application/pdf')",
                            "default": "application/octet-stream"
                        },
                        "encoding": {
                            "type": "string",
                            "enum": ["utf-8", "base64"],
                            "description": "Content encoding. Use base64 for binary data.",
                            "default": "utf-8"
                        }
                    },
                    "required": ["filename", "content", "org_id"]
                }),
            },
            ToolDef {
                name: "memory_store".into(),
                description: "Store a fact or memory in the Vektori vector store. \
                    The content is embedded and indexed for later semantic retrieval."
                    .into(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The text content to store"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Namespace for scoping the memory (e.g. 'workflow:abc:entity:xyz')"
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow ID for scoping"
                        },
                        "entity_key": {
                            "type": "string",
                            "description": "Entity key within the workflow"
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Optional key-value metadata",
                            "additionalProperties": { "type": "string" }
                        }
                    },
                    "required": ["content", "namespace"]
                }),
            },
            ToolDef {
                name: "memory_query".into(),
                description: "Search the Vektori vector store for semantically similar content. \
                    Returns ranked results with cosine similarity scores."
                    .into(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query text"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Namespace to search within"
                        },
                        "workflow_id": {
                            "type": "string",
                            "description": "Workflow ID for scoping"
                        },
                        "entity_key": {
                            "type": "string",
                            "description": "Entity key for scoping"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "min_score": {
                            "type": "number",
                            "description": "Minimum cosine similarity threshold (0.0 to 1.0)",
                            "default": 0.0
                        }
                    },
                    "required": ["query", "namespace"]
                }),
            },
            ToolDef {
                name: "slack_post".into(),
                description: "Post a message to a Slack channel. Requires the Slack \
                    integration to be connected for the organization."
                    .into(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "channel": {
                            "type": "string",
                            "description": "Channel ID (e.g. 'C0123456789') or name (e.g. '#general')"
                        },
                        "text": {
                            "type": "string",
                            "description": "Message text (supports mrkdwn formatting)"
                        },
                        "org_id": {
                            "type": "string",
                            "description": "Organization ID (for credential lookup)"
                        },
                        "blocks": {
                            "type": "array",
                            "description": "Optional Block Kit blocks for rich formatting",
                            "items": { "type": "object" }
                        }
                    },
                    "required": ["channel", "text", "org_id"]
                }),
            },
            ToolDef {
                name: "github_pr_comment".into(),
                description: "Post a comment on a GitHub pull request. Requires the \
                    GitHub integration to be connected for the organization."
                    .into(),
                parameters: serde_json::json!({
                    "type": "object",
                    "properties": {
                        "repo": {
                            "type": "string",
                            "description": "Repository in 'owner/repo' format (e.g. 'devsper/platform')"
                        },
                        "pr_number": {
                            "type": "integer",
                            "description": "Pull request number"
                        },
                        "body": {
                            "type": "string",
                            "description": "Comment body (supports GitHub Flavored Markdown)"
                        },
                        "org_id": {
                            "type": "string",
                            "description": "Organization ID (for credential lookup)"
                        }
                    },
                    "required": ["repo", "pr_number", "body", "org_id"]
                }),
            },
        ]
    }
}

#[async_trait]
impl ToolExecutor for StandardTools {
    async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
        match call.name.as_str() {
            "http_request" => self.execute_http_request(call).await,
            "file_read" => self.execute_file_read(call).await,
            "file_write" => self.execute_file_write(call).await,
            "memory_store" => self.execute_memory_store(call).await,
            "memory_query" => self.execute_memory_query(call).await,
            "slack_post" => self.execute_slack_post(call).await,
            "github_pr_comment" => self.execute_github_pr_comment(call).await,
            _ => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({
                    "error": format!("unknown standard tool: {}", call.name)
                }),
                is_error: true,
            }),
        }
    }

    fn list_tools(&self) -> Vec<ToolDef> {
        Self::tool_definitions()
    }
}

// ---------------------------------------------------------------------------
// Standard tool execute implementations
// ---------------------------------------------------------------------------
// Each execute method builds a request to the Go platform integration service.
// When the platform URL is not configured, a stub response is returned.

impl StandardTools {
    /// Sends a callback request to the platform integration service.
    async fn platform_callback(
        &self,
        path: &str,
        body: serde_json::Value,
    ) -> Result<serde_json::Value> {
        if self.callback.platform_url.is_empty() {
            return Ok(serde_json::json!({
                "status": "stub",
                "message": "platform URL not configured; tool call not forwarded"
            }));
        }

        let url = format!(
            "{}/{}",
            self.callback.platform_url.trim_end_matches('/'),
            path.trim_start_matches('/')
        );

        let mut req = self.http.post(&url);
        if let Some(ref secret) = self.callback.internal_secret {
            req = req.header("X-Platform-Internal-Secret", secret);
        }

        let resp = req
            .json(&body)
            .send()
            .await
            .map_err(|e| anyhow::anyhow!("platform callback failed: {}", e))?;

        let status = resp.status();
        let resp_body: serde_json::Value = resp
            .json()
            .await
            .unwrap_or_else(|_| serde_json::json!({"error": "failed to parse response"}));

        if !status.is_success() {
            anyhow::bail!("platform callback returned {}: {}", status, resp_body);
        }

        Ok(resp_body)
    }

    async fn execute_http_request(&self, call: ToolCall) -> Result<ToolResult> {
        let args = &call.arguments;
        let method = args.get("method").and_then(|v| v.as_str()).unwrap_or("GET");
        let url = args.get("url").and_then(|v| v.as_str()).unwrap_or("");
        let service = args
            .get("service")
            .and_then(|v| v.as_str())
            .unwrap_or("generic");

        if url.is_empty() {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "url is required"}),
                is_error: true,
            });
        }

        let result = self
            .platform_callback(
                "tools/http_request",
                serde_json::json!({
                    "method": method,
                    "url": url,
                    "service": service,
                    "headers": args.get("headers").cloned().unwrap_or(serde_json::json!({})),
                    "body": args.get("body").cloned().unwrap_or(serde_json::Value::Null),
                }),
            )
            .await;

        match result {
            Ok(resp) => Ok(ToolResult {
                tool_call_id: call.id,
                content: resp,
                is_error: false,
            }),
            Err(e) => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": e.to_string()}),
                is_error: true,
            }),
        }
    }

    async fn execute_file_read(&self, call: ToolCall) -> Result<ToolResult> {
        let args = &call.arguments;
        let object_key = args
            .get("object_key")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let org_id = args.get("org_id").and_then(|v| v.as_str()).unwrap_or("");

        if object_key.is_empty() || org_id.is_empty() {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "object_key and org_id are required"}),
                is_error: true,
            });
        }

        let result = self
            .platform_callback(
                "tools/file_read",
                serde_json::json!({
                    "object_key": object_key,
                    "org_id": org_id,
                    "encoding": args.get("encoding").and_then(|v| v.as_str()).unwrap_or("utf-8"),
                }),
            )
            .await;

        match result {
            Ok(resp) => Ok(ToolResult {
                tool_call_id: call.id,
                content: resp,
                is_error: false,
            }),
            Err(e) => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": e.to_string()}),
                is_error: true,
            }),
        }
    }

    async fn execute_file_write(&self, call: ToolCall) -> Result<ToolResult> {
        let args = &call.arguments;
        let filename = args.get("filename").and_then(|v| v.as_str()).unwrap_or("");
        let org_id = args.get("org_id").and_then(|v| v.as_str()).unwrap_or("");

        if filename.is_empty() || org_id.is_empty() {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "filename and org_id are required"}),
                is_error: true,
            });
        }

        let result = self.platform_callback("tools/file_write", serde_json::json!({
            "filename": filename,
            "content": args.get("content"),
            "org_id": org_id,
            "content_type": args.get("content_type").and_then(|v| v.as_str()).unwrap_or("application/octet-stream"),
            "encoding": args.get("encoding").and_then(|v| v.as_str()).unwrap_or("utf-8"),
        })).await;

        match result {
            Ok(resp) => Ok(ToolResult {
                tool_call_id: call.id,
                content: resp,
                is_error: false,
            }),
            Err(e) => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": e.to_string()}),
                is_error: true,
            }),
        }
    }

    async fn execute_memory_store(&self, call: ToolCall) -> Result<ToolResult> {
        let args = &call.arguments;
        let content = args.get("content").and_then(|v| v.as_str()).unwrap_or("");
        let namespace = args.get("namespace").and_then(|v| v.as_str()).unwrap_or("");

        if content.is_empty() || namespace.is_empty() {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "content and namespace are required"}),
                is_error: true,
            });
        }

        let result = self
            .platform_callback(
                "tools/memory_store",
                serde_json::json!({
                    "content": content,
                    "namespace": namespace,
                    "workflow_id": args.get("workflow_id").and_then(|v| v.as_str()).unwrap_or(""),
                    "entity_key": args.get("entity_key").and_then(|v| v.as_str()).unwrap_or(""),
                    "metadata": args.get("metadata").cloned().unwrap_or(serde_json::json!({})),
                }),
            )
            .await;

        match result {
            Ok(resp) => Ok(ToolResult {
                tool_call_id: call.id,
                content: resp,
                is_error: false,
            }),
            Err(e) => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": e.to_string()}),
                is_error: true,
            }),
        }
    }

    async fn execute_memory_query(&self, call: ToolCall) -> Result<ToolResult> {
        let args = &call.arguments;
        let query = args.get("query").and_then(|v| v.as_str()).unwrap_or("");
        let namespace = args.get("namespace").and_then(|v| v.as_str()).unwrap_or("");

        if query.is_empty() || namespace.is_empty() {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "query and namespace are required"}),
                is_error: true,
            });
        }

        let result = self
            .platform_callback(
                "tools/memory_query",
                serde_json::json!({
                    "query": query,
                    "namespace": namespace,
                    "workflow_id": args.get("workflow_id").and_then(|v| v.as_str()).unwrap_or(""),
                    "entity_key": args.get("entity_key").and_then(|v| v.as_str()).unwrap_or(""),
                    "top_k": args.get("top_k").and_then(|v| v.as_u64()).unwrap_or(10),
                    "min_score": args.get("min_score").and_then(|v| v.as_f64()).unwrap_or(0.0),
                }),
            )
            .await;

        match result {
            Ok(resp) => Ok(ToolResult {
                tool_call_id: call.id,
                content: resp,
                is_error: false,
            }),
            Err(e) => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": e.to_string()}),
                is_error: true,
            }),
        }
    }

    async fn execute_slack_post(&self, call: ToolCall) -> Result<ToolResult> {
        let args = &call.arguments;
        let channel = args.get("channel").and_then(|v| v.as_str()).unwrap_or("");
        let text = args.get("text").and_then(|v| v.as_str()).unwrap_or("");
        let org_id = args.get("org_id").and_then(|v| v.as_str()).unwrap_or("");

        if channel.is_empty() || text.is_empty() || org_id.is_empty() {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "channel, text, and org_id are required"}),
                is_error: true,
            });
        }

        let result = self
            .platform_callback(
                "tools/slack_post",
                serde_json::json!({
                    "channel": channel,
                    "text": text,
                    "org_id": org_id,
                    "blocks": args.get("blocks").cloned().unwrap_or(serde_json::json!([])),
                }),
            )
            .await;

        match result {
            Ok(resp) => Ok(ToolResult {
                tool_call_id: call.id,
                content: resp,
                is_error: false,
            }),
            Err(e) => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": e.to_string()}),
                is_error: true,
            }),
        }
    }

    async fn execute_github_pr_comment(&self, call: ToolCall) -> Result<ToolResult> {
        let args = &call.arguments;
        let repo = args.get("repo").and_then(|v| v.as_str()).unwrap_or("");
        let body = args.get("body").and_then(|v| v.as_str()).unwrap_or("");
        let org_id = args.get("org_id").and_then(|v| v.as_str()).unwrap_or("");

        if repo.is_empty() || body.is_empty() || org_id.is_empty() {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "repo, body, and org_id are required"}),
                is_error: true,
            });
        }

        let pr_number = args.get("pr_number").and_then(|v| v.as_u64()).unwrap_or(0);

        if pr_number == 0 {
            return Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": "pr_number must be a positive integer"}),
                is_error: true,
            });
        }

        let result = self
            .platform_callback(
                "tools/github_pr_comment",
                serde_json::json!({
                    "repo": repo,
                    "pr_number": pr_number,
                    "body": body,
                    "org_id": org_id,
                }),
            )
            .await;

        match result {
            Ok(resp) => Ok(ToolResult {
                tool_call_id: call.id,
                content: resp,
                is_error: false,
            }),
            Err(e) => Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!({"error": e.to_string()}),
                is_error: true,
            }),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use devsper_core::{ToolCall, ToolDef, ToolResult};
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn make_call() -> ToolCall {
        ToolCall {
            id: "tc-1".to_string(),
            name: "test_tool".to_string(),
            arguments: serde_json::json!({}),
        }
    }

    struct SlowTool {
        delay_ms: u64,
        call_count: Arc<AtomicUsize>,
    }

    #[async_trait]
    impl ToolExecutor for SlowTool {
        async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
            self.call_count.fetch_add(1, Ordering::SeqCst);
            tokio::time::sleep(Duration::from_millis(self.delay_ms)).await;
            Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!("ok"),
                is_error: false,
            })
        }
        fn list_tools(&self) -> Vec<ToolDef> {
            vec![]
        }
    }

    struct FailingTool {
        call_count: Arc<AtomicUsize>,
    }

    #[async_trait]
    impl ToolExecutor for FailingTool {
        async fn execute(&self, _call: ToolCall) -> Result<ToolResult> {
            self.call_count.fetch_add(1, Ordering::SeqCst);
            Err(anyhow::anyhow!("tool error"))
        }
        fn list_tools(&self) -> Vec<ToolDef> {
            vec![]
        }
    }

    struct OkTool;

    #[async_trait]
    impl ToolExecutor for OkTool {
        async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
            Ok(ToolResult {
                tool_call_id: call.id,
                content: serde_json::json!("done"),
                is_error: false,
            })
        }
        fn list_tools(&self) -> Vec<ToolDef> {
            vec![]
        }
    }

    #[tokio::test]
    async fn timeout_returns_error_result() {
        let count = Arc::new(AtomicUsize::new(0));
        let inner = Arc::new(SlowTool {
            delay_ms: 500,
            call_count: count,
        });
        let executor = HardenedToolExecutor::new(
            inner,
            ToolPolicy {
                timeout_ms: 50,
                max_retries: 0,
                retry_delay_ms: 0,
            },
        );
        let result = executor.execute(make_call()).await.unwrap();
        assert!(result.is_error);
        assert!(result.content["error"]
            .as_str()
            .unwrap()
            .contains("timed out"));
    }

    #[tokio::test]
    async fn retries_on_failure() {
        let count = Arc::new(AtomicUsize::new(0));
        let inner = Arc::new(FailingTool {
            call_count: count.clone(),
        });
        let executor = HardenedToolExecutor::new(
            inner,
            ToolPolicy {
                timeout_ms: 1000,
                max_retries: 2,
                retry_delay_ms: 10,
            },
        );
        let result = executor.execute(make_call()).await.unwrap();
        assert!(result.is_error);
        assert_eq!(
            count.load(Ordering::SeqCst),
            3,
            "initial + 2 retries = 3 total"
        );
    }

    #[tokio::test]
    async fn succeeds_on_first_attempt() {
        let executor = HardenedToolExecutor::new(Arc::new(OkTool), ToolPolicy::default());
        let result = executor.execute(make_call()).await.unwrap();
        assert!(!result.is_error);
        assert_eq!(result.content, serde_json::json!("done"));
    }

    #[tokio::test]
    async fn list_tools_delegates_to_inner() {
        struct ToolLister;
        #[async_trait]
        impl ToolExecutor for ToolLister {
            async fn execute(&self, call: ToolCall) -> Result<ToolResult> {
                Ok(ToolResult {
                    tool_call_id: call.id,
                    content: serde_json::json!(null),
                    is_error: false,
                })
            }
            fn list_tools(&self) -> Vec<ToolDef> {
                vec![ToolDef {
                    name: "my_tool".to_string(),
                    description: "does things".to_string(),
                    parameters: serde_json::json!({}),
                }]
            }
        }
        let executor = HardenedToolExecutor::new(Arc::new(ToolLister), ToolPolicy::default());
        let tools = executor.list_tools();
        assert_eq!(tools.len(), 1);
        assert_eq!(tools[0].name, "my_tool");
    }

    // --- Standard tools tests ---

    #[tokio::test]
    async fn standard_tools_lists_all_seven_tools() {
        let tools = StandardTools::new(PlatformCallbackConfig::default());
        let defs = tools.list_tools();
        assert_eq!(defs.len(), 7);

        let names: Vec<&str> = defs.iter().map(|d| d.name.as_str()).collect();
        assert!(names.contains(&"http_request"));
        assert!(names.contains(&"file_read"));
        assert!(names.contains(&"file_write"));
        assert!(names.contains(&"memory_store"));
        assert!(names.contains(&"memory_query"));
        assert!(names.contains(&"slack_post"));
        assert!(names.contains(&"github_pr_comment"));
    }

    #[tokio::test]
    async fn standard_tools_validates_required_params() {
        let tools = StandardTools::new(PlatformCallbackConfig::default());

        // http_request with empty URL should error.
        let call = ToolCall {
            id: "tc-1".into(),
            name: "http_request".into(),
            arguments: serde_json::json!({"method": "GET", "url": ""}),
        };
        let result = tools.execute(call).await.unwrap();
        assert!(result.is_error);
        assert!(result.content["error"]
            .as_str()
            .unwrap()
            .contains("url is required"));

        // slack_post missing channel should error.
        let call = ToolCall {
            id: "tc-2".into(),
            name: "slack_post".into(),
            arguments: serde_json::json!({"text": "hello", "org_id": "org-1"}),
        };
        let result = tools.execute(call).await.unwrap();
        assert!(result.is_error);

        // github_pr_comment missing repo should error.
        let call = ToolCall {
            id: "tc-3".into(),
            name: "github_pr_comment".into(),
            arguments: serde_json::json!({"pr_number": 42, "body": "LGTM", "org_id": "org-1"}),
        };
        let result = tools.execute(call).await.unwrap();
        assert!(result.is_error);
    }

    #[tokio::test]
    async fn standard_tools_returns_stub_without_platform() {
        let tools = StandardTools::new(PlatformCallbackConfig::default());

        let call = ToolCall {
            id: "tc-4".into(),
            name: "memory_query".into(),
            arguments: serde_json::json!({
                "query": "test query",
                "namespace": "test"
            }),
        };
        let result = tools.execute(call).await.unwrap();
        assert!(!result.is_error);
        assert_eq!(result.content["status"], "stub");
    }

    #[tokio::test]
    async fn standard_tools_unknown_tool_returns_error() {
        let tools = StandardTools::new(PlatformCallbackConfig::default());

        let call = ToolCall {
            id: "tc-5".into(),
            name: "nonexistent_tool".into(),
            arguments: serde_json::json!({}),
        };
        let result = tools.execute(call).await.unwrap();
        assert!(result.is_error);
        assert!(result.content["error"]
            .as_str()
            .unwrap()
            .contains("unknown standard tool"));
    }

    #[test]
    fn standard_tool_definitions_have_valid_schemas() {
        let defs = StandardTools::tool_definitions();
        for def in &defs {
            assert!(!def.name.is_empty(), "tool name must not be empty");
            assert!(
                !def.description.is_empty(),
                "tool description must not be empty"
            );
            // Parameters should be a JSON object with at least "type" and "properties".
            assert_eq!(def.parameters["type"], "object");
            assert!(
                def.parameters.get("properties").is_some(),
                "tool {} missing properties",
                def.name
            );
        }
    }
}
