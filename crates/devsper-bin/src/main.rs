use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "devsper", about = "Devsper runtime — self-evolving AI workflow engine")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// Run a .devsper workflow
    Run {
        /// Path to .devsper file
        spec: String,
    },
    /// Compile a .devsper file to bytecode or standalone binary
    Compile {
        /// Path to .devsper file
        spec: String,
        /// Embed runtime into standalone binary
        #[arg(long)]
        embed: bool,
    },
    /// Join or start a peer cluster node
    Peer {
        /// Address to listen on
        #[arg(long)]
        listen: Option<String>,
        /// Address of existing cluster node to join
        #[arg(long)]
        join: Option<String>,
    },
    /// Inspect a running workflow
    Inspect {
        /// Run ID to inspect
        run_id: String,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    match cli.command {
        Command::Run { spec } => {
            println!("TODO: run {spec}");
        }
        Command::Compile { spec, embed } => {
            println!("TODO: compile {spec} (embed={embed})");
        }
        Command::Peer { listen, join } => {
            println!("TODO: peer listen={listen:?} join={join:?}");
        }
        Command::Inspect { run_id } => {
            println!("TODO: inspect {run_id}");
        }
    }
    Ok(())
}
