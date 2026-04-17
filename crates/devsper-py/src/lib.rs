use devsper_compiler::{WorkflowIr as RustWorkflowIr, WorkflowLoader};
use devsper_core::{
    LlmMessage, LlmProvider, LlmRequest, LlmRole, NodeId, NodeSpec as RustNodeSpec, RunId,
};
use devsper_executor::{AgentFn, AgentOutput, Executor, ExecutorConfig};
use devsper_graph::{GraphActor, GraphConfig};
use devsper_providers::{
    anthropic::AnthropicProvider, ollama::OllamaProvider, openai::OpenAiProvider,
    AzureFoundryProvider, AzureOpenAiProvider, GithubModelsProvider, LiteLlmProvider, MockProvider,
    ModelRouter,
};
use devsper_scheduler::Scheduler;
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use std::collections::HashMap;
use std::sync::Arc;

// ── Helpers ───────────────────────────────────────────────────────────────────

/// Build a ModelRouter from environment variables, mirroring run_command in main.rs.
fn build_router() -> (Arc<ModelRouter>, bool) {
    let mut router = ModelRouter::new();
    let mut has_real = false;

    if let Ok(key) = std::env::var("ANTHROPIC_API_KEY") {
        router.add_provider(Arc::new(AnthropicProvider::new(key)));
        has_real = true;
    }
    if let Ok(key) = std::env::var("OPENAI_API_KEY") {
        router.add_provider(Arc::new(OpenAiProvider::new(key)));
        has_real = true;
    }
    if let Ok(key) = std::env::var("ZAI_API_KEY") {
        let base = std::env::var("ZAI_BASE_URL")
            .unwrap_or_else(|_| "https://api.z.ai/v1".into());
        router.add_provider(Arc::new(OpenAiProvider::zai(key).with_base_url(base)));
        has_real = true;
    }
    if let Ok(token) = std::env::var("GITHUB_TOKEN") {
        router.add_provider(Arc::new(GithubModelsProvider::new(token)));
        has_real = true;
    }
    if let (Ok(key), Ok(endpoint), Ok(deployment)) = (
        std::env::var("AZURE_OPENAI_API_KEY"),
        std::env::var("AZURE_OPENAI_ENDPOINT"),
        std::env::var("AZURE_OPENAI_DEPLOYMENT"),
    ) {
        let api_version = std::env::var("AZURE_OPENAI_API_VERSION")
            .unwrap_or_else(|_| "2024-02-01".into());
        router.add_provider(Arc::new(AzureOpenAiProvider::new(
            key,
            endpoint,
            deployment,
            api_version,
        )));
        has_real = true;
    }
    if let (Ok(key), Ok(endpoint), Ok(deployment)) = (
        std::env::var("AZURE_FOUNDRY_API_KEY"),
        std::env::var("AZURE_FOUNDRY_ENDPOINT"),
        std::env::var("AZURE_FOUNDRY_DEPLOYMENT"),
    ) {
        router.add_provider(Arc::new(AzureFoundryProvider::new(key, endpoint, deployment)));
        has_real = true;
    }
    if let Ok(base_url) = std::env::var("LITELLM_BASE_URL") {
        let api_key = std::env::var("LITELLM_API_KEY").unwrap_or_default();
        router.add_provider(Arc::new(LiteLlmProvider::new(base_url, api_key)));
        has_real = true;
    }
    let ollama_host = std::env::var("OLLAMA_HOST")
        .unwrap_or_else(|_| "http://localhost:11434".into());
    router.add_provider(Arc::new(OllamaProvider::new().with_base_url(ollama_host)));
    router.add_provider(Arc::new(MockProvider::new("[Task completed by agent]")));

    (Arc::new(router), has_real)
}

/// Build an AgentFn from a router.
fn build_agent_fn(router: Arc<ModelRouter>, use_mock: bool) -> AgentFn {
    Arc::new(move |spec: RustNodeSpec| {
        let provider = router.clone();
        Box::pin(async move {
            let model = if use_mock {
                "mock".to_string()
            } else {
                spec.model.as_deref().unwrap_or("mock").to_string()
            };
            let req = LlmRequest {
                model,
                messages: vec![LlmMessage {
                    role: LlmRole::User,
                    content: spec.prompt.clone(),
                }],
                tools: vec![],
                max_tokens: Some(4096),
                temperature: None,
                system: None,
            };
            match provider.generate(req).await {
                Ok(resp) => Ok(AgentOutput {
                    result: serde_json::json!({ "content": resp.content }),
                    mutations: vec![],
                }),
                Err(e) => Err(e.to_string()),
            }
        })
    })
}

/// Execute a WorkflowIr and return {node_id → output} results map.
async fn execute_ir(ir: RustWorkflowIr) -> anyhow::Result<HashMap<String, String>> {
    let run_id = RunId::new();

    let graph_config = GraphConfig {
        run_id: run_id.clone(),
        snapshot_interval: 1000,
        max_depth: ir.evolution.max_depth,
    };
    let (mut actor, handle, _events) = GraphActor::new(graph_config);

    // Map IR task ids → fresh NodeIds and build specs
    let task_id_map: HashMap<String, NodeId> = ir
        .tasks
        .iter()
        .map(|t| (t.id.clone(), NodeId::new()))
        .collect();

    let specs: Vec<RustNodeSpec> = ir
        .tasks
        .iter()
        .map(|t| {
            let id = task_id_map[&t.id].clone();
            let deps: Vec<NodeId> = t
                .depends_on
                .iter()
                .filter_map(|dep| task_id_map.get(dep).cloned())
                .collect();
            RustNodeSpec::new(t.prompt.clone())
                .with_id(id)
                .with_model(t.model.as_deref().unwrap_or(&ir.model))
                .depends_on(deps)
        })
        .collect();

    // Capture node id → task ir id mapping for result collection
    let node_to_task: HashMap<NodeId, String> = task_id_map
        .iter()
        .map(|(task_id, node_id)| (node_id.clone(), task_id.clone()))
        .collect();

    actor.add_initial_nodes(specs);
    tokio::spawn(actor.run());

    let (router, has_real) = build_router();
    let agent_fn = build_agent_fn(router, !has_real);

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = Executor::new(
        ExecutorConfig {
            worker_count: ir.workers,
            poll_interval_ms: 50,
        },
        scheduler,
        handle.clone(),
        agent_fn,
    );

    executor.run().await?;

    // Collect results from snapshot
    let snap = handle.snapshot().await;
    let mut results = HashMap::new();
    if let Some(snap) = snap {
        for (node_id, node) in &snap.nodes {
            let key = node_to_task
                .get(node_id)
                .cloned()
                .unwrap_or_else(|| node_id.0.clone());
            let value = node
                .result
                .as_ref()
                .and_then(|r| r.get("content"))
                .and_then(|c| c.as_str())
                .unwrap_or("")
                .to_string();
            results.insert(key, value);
        }
    }

    Ok(results)
}

/// Execute a list of NodeSpecs directly and return results.
async fn execute_specs(specs: Vec<RustNodeSpec>) -> anyhow::Result<HashMap<String, String>> {
    let run_id = RunId::new();
    let graph_config = GraphConfig {
        run_id: run_id.clone(),
        snapshot_interval: 1000,
        max_depth: 10,
    };
    let (mut actor, handle, _events) = GraphActor::new(graph_config);

    let node_ids: Vec<NodeId> = specs.iter().map(|s| s.id.clone()).collect();
    actor.add_initial_nodes(specs);
    tokio::spawn(actor.run());

    let (router, has_real) = build_router();
    let agent_fn = build_agent_fn(router, !has_real);

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = Executor::new(
        ExecutorConfig::default(),
        scheduler,
        handle.clone(),
        agent_fn,
    );

    executor.run().await?;

    let snap = handle.snapshot().await;
    let mut results = HashMap::new();
    if let Some(snap) = snap {
        for node_id in &node_ids {
            let node = snap.nodes.get(node_id);
            let value = node
                .and_then(|n| n.result.as_ref())
                .and_then(|r| r.get("content"))
                .and_then(|c| c.as_str())
                .unwrap_or("")
                .to_string();
            results.insert(node_id.0.clone(), value);
        }
    }

    Ok(results)
}

// ── Python classes ────────────────────────────────────────────────────────────

/// Python-visible NodeSpec.
#[pyclass(name = "NodeSpec")]
#[derive(Clone)]
pub struct PyNodeSpec {
    inner: RustNodeSpec,
}

#[pymethods]
impl PyNodeSpec {
    #[new]
    #[pyo3(signature = (prompt, model=None, depends_on=None))]
    fn new(
        prompt: String,
        model: Option<String>,
        depends_on: Option<Vec<PyRef<PyNodeSpec>>>,
    ) -> Self {
        let mut spec = RustNodeSpec::new(prompt);
        if let Some(m) = model {
            spec = spec.with_model(m);
        }
        if let Some(deps) = depends_on {
            let dep_ids: Vec<NodeId> = deps.iter().map(|d| d.inner.id.clone()).collect();
            spec = spec.depends_on(dep_ids);
        }
        Self { inner: spec }
    }

    #[getter]
    fn prompt(&self) -> &str {
        &self.inner.prompt
    }

    #[getter]
    fn model(&self) -> Option<&str> {
        self.inner.model.as_deref()
    }

    #[getter]
    fn id(&self) -> &str {
        &self.inner.id.0
    }
}

/// Python-visible WorkflowIr — stores IR as JSON internally to avoid Clone issues.
#[pyclass(name = "WorkflowIr")]
pub struct PyWorkflowIr {
    // Store as JSON string to sidestep any Clone/Send boundary issues
    json: String,
}

impl PyWorkflowIr {
    fn to_rust(&self) -> PyResult<RustWorkflowIr> {
        serde_json::from_str(&self.json)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to deserialize WorkflowIr: {e}")))
    }
}

#[pymethods]
impl PyWorkflowIr {
    #[getter]
    fn name(&self) -> PyResult<String> {
        let ir = self.to_rust()?;
        Ok(ir.name)
    }

    #[getter]
    fn model(&self) -> PyResult<String> {
        let ir = self.to_rust()?;
        Ok(ir.model)
    }

    #[getter]
    fn tasks(&self) -> PyResult<Vec<HashMap<String, String>>> {
        let ir = self.to_rust()?;
        Ok(ir.tasks.iter().map(|t| {
            let mut m = HashMap::new();
            m.insert("id".to_string(), t.id.clone());
            m.insert("prompt".to_string(), t.prompt.clone());
            if let Some(model) = &t.model {
                m.insert("model".to_string(), model.clone());
            }
            m
        }).collect())
    }
}

// ── Free functions ────────────────────────────────────────────────────────────

/// Load and run a workflow file. Returns {task_id: output} dict. Blocking.
#[pyfunction]
#[pyo3(signature = (workflow_path, inputs=None))]
fn run(
    py: Python<'_>,
    workflow_path: String,
    inputs: Option<HashMap<String, String>>,
) -> PyResult<HashMap<String, String>> {
    let _ = inputs; // inputs are parsed but not yet threaded through IR
    let path = std::path::Path::new(&workflow_path);
    let ir = WorkflowLoader::load(path)
        .map_err(|e| PyRuntimeError::new_err(format!("Failed to load workflow: {e}")))?;

    py.allow_threads(|| {
        tokio::runtime::Runtime::new()
            .map_err(|e| PyRuntimeError::new_err(format!("Tokio runtime error: {e}")))?
            .block_on(execute_ir(ir))
            .map_err(|e| PyRuntimeError::new_err(format!("Execution error: {e}")))
    })
}

/// Async version of run().
#[pyfunction]
#[pyo3(signature = (workflow_path, inputs=None))]
fn run_async<'py>(
    py: Python<'py>,
    workflow_path: String,
    inputs: Option<HashMap<String, String>>,
) -> PyResult<Bound<'py, PyAny>> {
    let _ = inputs;
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        let path = std::path::Path::new(&workflow_path);
        let ir = WorkflowLoader::load(path)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to load workflow: {e}")))?;
        execute_ir(ir)
            .await
            .map_err(|e| PyRuntimeError::new_err(format!("Execution error: {e}")))
    })
}

/// Load and parse a .devsper workflow file into a WorkflowIr object.
#[pyfunction]
fn load_workflow(path: String) -> PyResult<PyWorkflowIr> {
    let p = std::path::Path::new(&path);
    let ir = WorkflowLoader::load(p)
        .map_err(|e| PyRuntimeError::new_err(format!("Failed to load workflow: {e}")))?;
    let json = serde_json::to_string(&ir)
        .map_err(|e| PyRuntimeError::new_err(format!("Serialization error: {e}")))?;
    Ok(PyWorkflowIr { json })
}

/// Run a pre-loaded WorkflowIr. Blocking.
#[pyfunction]
fn run_workflow(py: Python<'_>, ir: &PyWorkflowIr) -> PyResult<HashMap<String, String>> {
    let rust_ir = ir.to_rust()?;
    py.allow_threads(|| {
        tokio::runtime::Runtime::new()
            .map_err(|e| PyRuntimeError::new_err(format!("Tokio runtime error: {e}")))?
            .block_on(execute_ir(rust_ir))
            .map_err(|e| PyRuntimeError::new_err(format!("Execution error: {e}")))
    })
}

/// Async version of run_workflow().
#[pyfunction]
fn run_workflow_async<'py>(py: Python<'py>, ir: &PyWorkflowIr) -> PyResult<Bound<'py, PyAny>> {
    let rust_ir = ir.to_rust()?;
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        execute_ir(rust_ir)
            .await
            .map_err(|e| PyRuntimeError::new_err(format!("Execution error: {e}")))
    })
}

/// Run a list of PyNodeSpec objects directly. Blocking.
#[pyfunction]
fn run_specs(py: Python<'_>, specs: Vec<PyRef<PyNodeSpec>>) -> PyResult<HashMap<String, String>> {
    let rust_specs: Vec<RustNodeSpec> = specs.iter().map(|s| s.inner.clone()).collect();
    py.allow_threads(|| {
        tokio::runtime::Runtime::new()
            .map_err(|e| PyRuntimeError::new_err(format!("Tokio runtime error: {e}")))?
            .block_on(execute_specs(rust_specs))
            .map_err(|e| PyRuntimeError::new_err(format!("Execution error: {e}")))
    })
}

/// Async version of run_specs().
#[pyfunction]
fn run_specs_async<'py>(
    py: Python<'py>,
    specs: Vec<PyRef<PyNodeSpec>>,
) -> PyResult<Bound<'py, PyAny>> {
    let rust_specs: Vec<RustNodeSpec> = specs.iter().map(|s| s.inner.clone()).collect();
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        execute_specs(rust_specs)
            .await
            .map_err(|e| PyRuntimeError::new_err(format!("Execution error: {e}")))
    })
}

// ── Module registration ───────────────────────────────────────────────────────

#[pymodule]
fn devsper(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyNodeSpec>()?;
    m.add_class::<PyWorkflowIr>()?;
    m.add_function(wrap_pyfunction!(run, m)?)?;
    m.add_function(wrap_pyfunction!(run_async, m)?)?;
    m.add_function(wrap_pyfunction!(load_workflow, m)?)?;
    m.add_function(wrap_pyfunction!(run_workflow, m)?)?;
    m.add_function(wrap_pyfunction!(run_workflow_async, m)?)?;
    m.add_function(wrap_pyfunction!(run_specs, m)?)?;
    m.add_function(wrap_pyfunction!(run_specs_async, m)?)?;
    Ok(())
}
