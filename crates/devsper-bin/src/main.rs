mod credentials;
mod auth;
mod eval;

use clap::{Parser, Subcommand};
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    name = "devsper",
    about = "Devsper runtime — self-evolving AI workflow engine",
    version = env!("CARGO_PKG_VERSION"),
)]
struct Cli {
    #[command(subcommand)]
    command: Command,

    /// Enable verbose logging
    #[arg(long, short = 'v', global = true)]
    verbose: bool,
}

#[derive(Subcommand)]
enum Command {
    /// Run a .devsper workflow (source or compiled .bin)
    Run {
        /// Path to .devsper file
        spec: PathBuf,

        /// Key=value inputs for the workflow
        #[arg(long = "input", value_parser = parse_key_val)]
        inputs: Vec<(String, String)>,

        /// Cluster address to submit run to (optional)
        #[arg(long)]
        cluster: Option<String>,

        /// Unix socket path for TUI inspection
        #[arg(long)]
        inspect_socket: Option<PathBuf>,
    },

    /// Compile a .devsper file to bytecode or standalone binary
    Compile {
        /// Path to .devsper file
        spec: PathBuf,

        /// Embed runtime into a standalone binary
        #[arg(long)]
        embed: bool,

        /// Output file path
        #[arg(long, short)]
        output: Option<PathBuf>,
    },

    /// Start a peer cluster node
    Peer {
        /// Address to listen on
        #[arg(long, default_value = "0.0.0.0:7000")]
        listen: String,

        /// Address of existing cluster node to join
        #[arg(long)]
        join: Option<String>,
    },

    /// Inspect a running workflow via its socket
    Inspect {
        /// Run ID or socket path
        run_id: String,
    },

    /// Manage provider credentials in the OS keychain
    Credentials {
        #[command(subcommand)]
        action: CredentialsCmd,
    },

    /// Authentication helpers (GitHub device flow, status)
    Auth {
        #[command(subcommand)]
        action: AuthCmd,
    },

    /// Evaluate a workflow against a dataset
    Eval {
        #[command(subcommand)]
        action: EvalCmd,
    },
}

#[derive(Subcommand)]
enum CredentialsCmd {
    /// Interactively set credentials for a provider
    Set { provider: String },
    /// List all providers and their credential status
    List,
    /// Remove all stored credentials for a provider
    Remove { provider: String },
}

#[derive(Subcommand)]
enum AuthCmd {
    /// Authenticate with GitHub via device flow
    Github,
    /// Show authentication status for all providers
    Status,
}

#[derive(Subcommand)]
enum EvalCmd {
    /// Run a workflow against a JSONL dataset
    Run {
        /// Path to the workflow file
        workflow: PathBuf,
        /// Path to JSONL dataset file
        #[arg(long)]
        dataset: PathBuf,
        /// Output JSONL results file
        #[arg(long, default_value = "eval_results.jsonl")]
        output: PathBuf,
    },
    /// Print a summary report from eval results
    Report {
        /// Input JSONL results file
        #[arg(long, default_value = "eval_results.jsonl")]
        input: PathBuf,
        /// Show only the last N results (0 = all)
        #[arg(long, default_value_t = 0)]
        last: usize,
    },
}

fn parse_key_val(s: &str) -> Result<(String, String), String> {
    s.split_once('=')
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .ok_or_else(|| format!("expected KEY=VALUE, got '{s}'"))
}

fn init_tracing(verbose: bool) -> Option<opentelemetry_sdk::trace::Tracer> {
    use opentelemetry::trace::TracerProvider as _;
    use opentelemetry_otlp::WithExportConfig;
    use tracing_subscriber::prelude::*;

    let level = if verbose { "debug" } else { "info" };
    let env_filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(level));

    let fmt_layer = tracing_subscriber::fmt::layer();

    if let Ok(endpoint) = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT") {
        let exporter = opentelemetry_otlp::new_exporter()
            .http()
            .with_endpoint(endpoint);

        let provider = opentelemetry_otlp::new_pipeline()
            .tracing()
            .with_exporter(exporter)
            .with_trace_config(
                opentelemetry_sdk::trace::Config::default().with_resource(
                    opentelemetry_sdk::Resource::new(vec![
                        opentelemetry::KeyValue::new("service.name", "devsper"),
                        opentelemetry::KeyValue::new(
                            "service.version",
                            env!("CARGO_PKG_VERSION"),
                        ),
                    ]),
                ),
            )
            .install_batch(opentelemetry_sdk::runtime::Tokio)
            .expect("OTEL tracer init failed");

        let tracer = provider.tracer("devsper");
        let otel_layer = tracing_opentelemetry::layer().with_tracer(tracer.clone());

        tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt_layer)
            .with(otel_layer)
            .init();

        Some(tracer)
    } else {
        tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt_layer)
            .init();
        None
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let _tracer = init_tracing(cli.verbose);

    match cli.command {
        Command::Run {
            spec,
            inputs,
            cluster,
            inspect_socket,
        } => run_command(spec, inputs, cluster, inspect_socket).await,
        Command::Compile {
            spec,
            embed,
            output,
        } => compile_command(spec, embed, output).await,
        Command::Peer { listen, join } => peer_command(listen, join).await,
        Command::Inspect { run_id } => inspect_command(run_id).await,
        Command::Credentials { action } => match action {
            CredentialsCmd::Set { provider } => {
                credentials::credentials_set(&provider);
                Ok(())
            }
            CredentialsCmd::List => {
                credentials::credentials_list();
                Ok(())
            }
            CredentialsCmd::Remove { provider } => {
                credentials::credentials_remove(&provider);
                Ok(())
            }
        },
        Command::Auth { action } => match action {
            AuthCmd::Github => auth::auth_github().await,
            AuthCmd::Status => auth::auth_status().await,
        },
        Command::Eval { action } => match action {
            EvalCmd::Run { workflow, dataset, output } => {
                eval::eval_run(workflow, dataset, output).await
            }
            EvalCmd::Report { input, last } => {
                eval::eval_report(input, last)
            }
        },
    }
}

async fn run_command(
    spec: PathBuf,
    inputs: Vec<(String, String)>,
    _cluster: Option<String>,
    _inspect_socket: Option<PathBuf>,
) -> anyhow::Result<()> {
    credentials::inject_credentials();

    use devsper_compiler::WorkflowLoader;
    use devsper_core::{LlmMessage, LlmProvider, LlmRequest, LlmRole, NodeId, NodeSpec, RunId};
    use devsper_executor::{AgentFn, AgentOutput, Executor, ExecutorConfig};
    use devsper_graph::{GraphActor, GraphConfig};
    use devsper_providers::{MockProvider, ModelRouter};
    use devsper_scheduler::Scheduler;
    use std::sync::Arc;

    if !inputs.is_empty() {
        tracing::debug!(count = inputs.len(), "Workflow inputs provided");
    }

    tracing::info!(spec = %spec.display(), "Loading workflow");
    let ir = WorkflowLoader::load(&spec)?;
    tracing::info!(name = %ir.name, tasks = ir.tasks.len(), "Workflow loaded");

    let run_id = RunId::new();
    tracing::info!(run_id = %run_id, "Starting run");

    // Build graph from IR
    let graph_config = GraphConfig {
        run_id: run_id.clone(),
        snapshot_interval: 1000,
        max_depth: ir.evolution.max_depth,
    };

    let (mut actor, handle, _events) = GraphActor::new(graph_config);

    // Convert IR tasks to NodeSpecs
    let task_id_map: std::collections::HashMap<String, NodeId> = ir
        .tasks
        .iter()
        .map(|t| (t.id.clone(), NodeId::new()))
        .collect();

    let specs: Vec<NodeSpec> = ir
        .tasks
        .iter()
        .map(|t| {
            let id = task_id_map[&t.id].clone();
            let deps: Vec<NodeId> = t
                .depends_on
                .iter()
                .filter_map(|dep_id| task_id_map.get(dep_id).cloned())
                .collect();

            NodeSpec::new(t.prompt.clone())
                .with_id(id)
                .with_model(t.model.as_deref().unwrap_or(&ir.model))
                .depends_on(deps)
        })
        .collect();

    actor.add_initial_nodes(specs);
    tokio::spawn(actor.run());

    // Build provider router — load real providers from env, fall back to mock
    use devsper_providers::{
        anthropic::AnthropicProvider,
        ollama::OllamaProvider,
        openai::OpenAiProvider,
        AzureFoundryProvider,
        AzureOpenAiProvider,
        GithubModelsProvider,
        LiteLlmProvider,
        LmStudioProvider,
    };
    let mut router = ModelRouter::new();
    let mut has_real_provider = false;
    if let Ok(key) = std::env::var("ANTHROPIC_API_KEY") {
        router.add_provider(Arc::new(AnthropicProvider::new(key)));
        has_real_provider = true;
    }
    if let Ok(key) = std::env::var("OPENAI_API_KEY") {
        router.add_provider(Arc::new(OpenAiProvider::new(key)));
        has_real_provider = true;
    }
    if let Ok(key) = std::env::var("ZAI_API_KEY") {
        let base = std::env::var("ZAI_BASE_URL")
            .unwrap_or_else(|_| "https://api.z.ai/v1".into());
        router.add_provider(Arc::new(OpenAiProvider::zai(key).with_base_url(base)));
        has_real_provider = true;
    }
    // GitHub Models
    if let Ok(token) = std::env::var("GITHUB_TOKEN") {
        router.add_provider(Arc::new(GithubModelsProvider::new(token)));
        has_real_provider = true;
    }
    // Azure OpenAI
    if let (Ok(key), Ok(endpoint), Ok(deployment)) = (
        std::env::var("AZURE_OPENAI_API_KEY"),
        std::env::var("AZURE_OPENAI_ENDPOINT"),
        std::env::var("AZURE_OPENAI_DEPLOYMENT"),
    ) {
        let api_version = std::env::var("AZURE_OPENAI_API_VERSION")
            .unwrap_or_else(|_| "2024-02-01".into());
        router.add_provider(Arc::new(AzureOpenAiProvider::new(key, endpoint, deployment, api_version)));
        has_real_provider = true;
    }
    // Azure AI Foundry
    if let (Ok(key), Ok(endpoint), Ok(deployment)) = (
        std::env::var("AZURE_FOUNDRY_API_KEY"),
        std::env::var("AZURE_FOUNDRY_ENDPOINT"),
        std::env::var("AZURE_FOUNDRY_DEPLOYMENT"),
    ) {
        router.add_provider(Arc::new(AzureFoundryProvider::new(key, endpoint, deployment)));
        has_real_provider = true;
    }
    // LiteLLM proxy
    if let Ok(base_url) = std::env::var("LITELLM_BASE_URL") {
        let api_key = std::env::var("LITELLM_API_KEY").unwrap_or_default();
        router.add_provider(Arc::new(LiteLlmProvider::new(base_url, api_key)));
        has_real_provider = true;
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
            has_real_provider = true;
        }
        router.add_provider(Arc::new(provider));
    }
    // Ollama — fallback provider when host explicitly set
    let ollama_explicit = std::env::var("OLLAMA_HOST").is_ok();
    let ollama_host = std::env::var("OLLAMA_HOST")
        .unwrap_or_else(|_| "http://localhost:11434".into());
    let ollama = OllamaProvider::new().with_base_url(ollama_host);
    let ollama = if ollama_explicit { has_real_provider = true; ollama.as_fallback() } else { ollama };
    router.add_provider(Arc::new(ollama));
    router.add_provider(Arc::new(MockProvider::new("[Task completed by agent]")));
    if !has_real_provider {
        tracing::warn!("No LLM provider keys found — using mock provider (set ANTHROPIC_API_KEY, OPENAI_API_KEY, ZAI_API_KEY, GITHUB_TOKEN, AZURE_*, LITELLM_BASE_URL, or LMSTUDIO_BASE_URL for real responses)");
    }
    let router = Arc::new(router);
    let use_mock = !has_real_provider;

    // Agent function: calls LLM with task prompt
    let router_clone = router.clone();
    let agent_fn: AgentFn = Arc::new(move |spec: NodeSpec| {
        let provider = router_clone.clone();
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
                Err(e) => return Err(e.to_string()),
            }
        })
    });

    let scheduler = Arc::new(Scheduler::new(handle.clone()));
    let executor = Executor::new(
        ExecutorConfig {
            worker_count: ir.workers,
            poll_interval_ms: 50,
        },
        scheduler,
        handle,
        agent_fn,
    );

    executor.run().await?;
    tracing::info!(run_id = %run_id, "Run complete");
    Ok(())
}

async fn compile_command(
    spec: PathBuf,
    embed: bool,
    output: Option<PathBuf>,
) -> anyhow::Result<()> {
    credentials::inject_credentials();

    use devsper_compiler::{CompileOptions, Compiler};

    if embed {
        tracing::info!("Embed mode not yet supported — compiling to bytecode");
    }

    let options = CompileOptions { embed, output };
    let compiler = Compiler::new(options);
    let output_path = compiler.compile_to_bytecode(&spec)?;
    println!("Compiled: {}", output_path.display());
    Ok(())
}

async fn peer_command(listen: String, join: Option<String>) -> anyhow::Result<()> {
    credentials::inject_credentials();

    use devsper_cluster::{ClusterConfig, ClusterNode};

    let config = ClusterConfig {
        listen_address: listen.clone(),
        known_peers: join.into_iter().collect(),
        ..Default::default()
    };

    let node = ClusterNode::new(config);
    tracing::info!(address = %listen, "Peer node started");

    if node.config.known_peers.is_empty() {
        node.become_coordinator().await;
        tracing::info!("No peers to join — became coordinator");
    }

    // Wait for Ctrl-C
    tokio::signal::ctrl_c().await?;
    tracing::info!("Peer node shutting down");
    Ok(())
}

async fn inspect_command(run_id: String) -> anyhow::Result<()> {
    credentials::inject_credentials();

    println!("Inspect run: {run_id}");
    println!(
        "(Unix socket inspection not yet wired — use --inspect-socket flag with devsper run)"
    );
    Ok(())
}
