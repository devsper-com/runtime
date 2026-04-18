use devsper_compiler::{WorkflowIr as RustWorkflowIr, WorkflowLoader};
use devsper_core::{
    LlmMessage, LlmProvider, LlmRequest, LlmRole, NodeId, NodeSpec as RustNodeSpec, RunId,
};
use devsper_executor::{AgentFn, AgentOutput, Executor, ExecutorConfig};
use devsper_graph::{GraphActor, GraphConfig};
use devsper_providers::{
    anthropic::AnthropicProvider, ollama::OllamaProvider, openai::OpenAiProvider,
    AzureFoundryProvider, AzureOpenAiProvider, GithubModelsProvider, LiteLlmProvider,
    LmStudioProvider, MockProvider, ModelRouter,
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
    // LM Studio — fallback provider when URL explicitly set
    {
        let lmstudio_explicit = std::env::var("LMSTUDIO_BASE_URL").is_ok();
        let base_url = std::env::var("LMSTUDIO_BASE_URL")
            .unwrap_or_else(|_| "http://localhost:1234".into());
        let api_key = std::env::var("LMSTUDIO_API_KEY").unwrap_or_default();
        let mut provider = LmStudioProvider::new().with_base_url(base_url);
        if !api_key.is_empty() {
            provider = provider.with_api_key(api_key);
        }
        if lmstudio_explicit {
            provider = provider.as_fallback();
            has_real = true;
        }
        router.add_provider(Arc::new(provider));
    }
    // Ollama — fallback provider when host explicitly set
    let ollama_explicit = std::env::var("OLLAMA_HOST").is_ok();
    let ollama_host = std::env::var("OLLAMA_HOST")
        .unwrap_or_else(|_| "http://localhost:11434".into());
    let ollama = OllamaProvider::new().with_base_url(ollama_host);
    let ollama = if ollama_explicit { has_real = true; ollama.as_fallback() } else { ollama };
    router.add_provider(Arc::new(ollama));
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
                max_tokens: Some(512),
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

/// Substitute {{key}} placeholders in a prompt with values from a map.
fn substitute(prompt: &str, vars: &HashMap<String, String>) -> String {
    let mut out = prompt.to_string();
    for (k, v) in vars {
        out = out.replace(&format!("{{{{{k}}}}}"), v);
    }
    out
}

/// Execute a WorkflowIr topologically, threading task outputs into downstream prompts.
/// Each "level" (tasks whose deps are all satisfied) runs in parallel.
async fn execute_ir(ir: RustWorkflowIr, inputs: HashMap<String, String>) -> anyhow::Result<HashMap<String, String>> {
    let (router, has_real) = build_router();
    let agent_fn = build_agent_fn(router, !has_real);

    // vars accumulates both user inputs and task outputs for {{key}} substitution
    let mut vars: HashMap<String, String> = inputs;
    let mut all_results: HashMap<String, String> = HashMap::new();
    let mut done: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut remaining = ir.tasks.clone();
    let default_model = ir.model.clone();

    while !remaining.is_empty() {
        let (ready, waiting): (Vec<_>, Vec<_>) = remaining
            .into_iter()
            .partition(|t| t.depends_on.iter().all(|dep| done.contains(dep)));

        if ready.is_empty() {
            return Err(anyhow::anyhow!("Cycle or unresolvable dependency in workflow"));
        }

        // Run this level in parallel
        let mut join_set = tokio::task::JoinSet::new();
        for task in &ready {
            let prompt = substitute(&task.prompt, &vars);
            let model = task.model.as_deref().unwrap_or(&default_model).to_string();
            let task_id = task.id.clone();
            let agent = agent_fn.clone();
            join_set.spawn(async move {
                let spec = RustNodeSpec::new(prompt).with_model(model);
                let result = agent(spec).await;
                (task_id, result)
            });
        }

        while let Some(res) = join_set.join_next().await {
            let (task_id, agent_result) = res.map_err(|e| anyhow::anyhow!("Task panicked: {e}"))?;
            let content = agent_result
                .map_err(|e| anyhow::anyhow!("Task {task_id} failed: {e}"))?
                .result
                .get("content")
                .and_then(|c| c.as_str())
                .unwrap_or("")
                .to_string();
            // Truncate task output used as template var to avoid context overflow in downstream tasks
            let var_val = if content.len() > 400 {
                format!("{}…[truncated]", &content[..400])
            } else {
                content.clone()
            };
            vars.insert(task_id.clone(), var_val);
            all_results.insert(task_id.clone(), content);
            done.insert(task_id);
        }

        remaining = waiting;
    }

    Ok(all_results)
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
    let inputs = inputs.unwrap_or_default();
    let path = std::path::Path::new(&workflow_path);
    let ir = WorkflowLoader::load(path)
        .map_err(|e| PyRuntimeError::new_err(format!("Failed to load workflow: {e}")))?;

    py.allow_threads(|| {
        tokio::runtime::Runtime::new()
            .map_err(|e| PyRuntimeError::new_err(format!("Tokio runtime error: {e}")))?
            .block_on(execute_ir(ir, inputs))
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
    let inputs = inputs.unwrap_or_default();
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        let path = std::path::Path::new(&workflow_path);
        let ir = WorkflowLoader::load(path)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to load workflow: {e}")))?;
        execute_ir(ir, inputs)
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
            .block_on(execute_ir(rust_ir, HashMap::new()))
            .map_err(|e| PyRuntimeError::new_err(format!("Execution error: {e}")))
    })
}

/// Async version of run_workflow().
#[pyfunction]
fn run_workflow_async<'py>(py: Python<'py>, ir: &PyWorkflowIr) -> PyResult<Bound<'py, PyAny>> {
    let rust_ir = ir.to_rust()?;
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        execute_ir(rust_ir, HashMap::new())
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

/// Compile a .devsper workflow to bytecode. Returns the output path.
#[pyfunction]
#[pyo3(signature = (spec_path, embed=false, output=None))]
fn compile(
    py: Python<'_>,
    spec_path: String,
    embed: bool,
    output: Option<String>,
) -> PyResult<String> {
    use devsper_compiler::{CompileOptions, Compiler};
    let spec = std::path::PathBuf::from(&spec_path);
    let opts = CompileOptions {
        embed,
        output: output.map(std::path::PathBuf::from),
    };
    py.allow_threads(|| {
        let compiler = Compiler::new(opts);
        compiler
            .compile_to_bytecode(&spec)
            .map(|p| p.to_string_lossy().into_owned())
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))
    })
}

/// Start a peer cluster node. Blocks until Ctrl-C.
#[pyfunction]
#[pyo3(signature = (listen=None, join=None))]
fn peer(py: Python<'_>, listen: Option<String>, join: Option<String>) -> PyResult<()> {
    use devsper_cluster::{ClusterConfig, ClusterNode};
    let listen = listen.unwrap_or_else(|| "0.0.0.0:7000".to_string());
    py.allow_threads(|| {
        tokio::runtime::Runtime::new()
            .map_err(|e| PyRuntimeError::new_err(e.to_string()))?
            .block_on(async {
                let config = ClusterConfig {
                    listen_address: listen.clone(),
                    known_peers: join.into_iter().collect(),
                    ..Default::default()
                };
                let node = ClusterNode::new(config);
                eprintln!("Peer node listening on {listen}");
                if node.config.known_peers.is_empty() {
                    node.become_coordinator().await;
                }
                tokio::signal::ctrl_c().await.ok();
                eprintln!("Peer node shutting down");
                Ok(())
            })
    })
}

/// Inspect a running workflow (stub — Unix socket not yet wired).
#[pyfunction]
fn inspect(run_id: String) -> PyResult<()> {
    println!("Inspect run: {run_id}");
    println!("(Unix socket inspection not yet wired — use --inspect-socket flag with devsper run)");
    Ok(())
}

// ── Module registration ───────────────────────────────────────────────────────

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyNodeSpec>()?;
    m.add_class::<PyWorkflowIr>()?;
    m.add_function(wrap_pyfunction!(run, m)?)?;
    m.add_function(wrap_pyfunction!(run_async, m)?)?;
    m.add_function(wrap_pyfunction!(load_workflow, m)?)?;
    m.add_function(wrap_pyfunction!(run_workflow, m)?)?;
    m.add_function(wrap_pyfunction!(run_workflow_async, m)?)?;
    m.add_function(wrap_pyfunction!(run_specs, m)?)?;
    m.add_function(wrap_pyfunction!(run_specs_async, m)?)?;
    m.add_function(wrap_pyfunction!(compile, m)?)?;
    m.add_function(wrap_pyfunction!(peer, m)?)?;
    m.add_function(wrap_pyfunction!(inspect, m)?)?;
    Ok(())
}
