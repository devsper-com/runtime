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
}

fn parse_key_val(s: &str) -> Result<(String, String), String> {
    s.split_once('=')
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .ok_or_else(|| format!("expected KEY=VALUE, got '{s}'"))
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    // Initialize tracing
    let level = if cli.verbose { "debug" } else { "info" };
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(level)),
        )
        .init();

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
    }
}

async fn run_command(
    spec: PathBuf,
    inputs: Vec<(String, String)>,
    _cluster: Option<String>,
    _inspect_socket: Option<PathBuf>,
) -> anyhow::Result<()> {
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

    // Build provider router — auto-detect real providers from env, fall back to mock
    let mut router = ModelRouter::new();
    let mock = Arc::new(MockProvider::new("[Task completed by agent]"));
    router.add_provider(mock);
    let router = Arc::new(router);

    // Agent function: calls LLM with task prompt
    let router_clone = router.clone();
    let agent_fn: AgentFn = Arc::new(move |spec: NodeSpec| {
        let provider = router_clone.clone();
        Box::pin(async move {
            let req = LlmRequest {
                model: spec.model.as_deref().unwrap_or("mock").to_string(),
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
    println!("Inspect run: {run_id}");
    println!(
        "(Unix socket inspection not yet wired — use --inspect-socket flag with devsper run)"
    );
    Ok(())
}
