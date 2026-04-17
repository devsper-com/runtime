# devsper

CLI for the devsper distributed AI swarm runtime.

```
devsper [OPTIONS] <COMMAND>
```

## Commands

### `run` — execute a workflow

```bash
devsper run my_workflow.devsper
devsper run my_workflow.devsper --input topic="quantum computing"
devsper run my_workflow.devsper --cluster http://coordinator:7000
```

### `compile` — compile to bytecode

```bash
devsper compile my_workflow.devsper
devsper compile my_workflow.devsper --output out.devsper.bin
devsper compile my_workflow.devsper --embed   # standalone binary
```

### `peer` — start a cluster node

```bash
# Start a standalone coordinator
devsper peer --listen 0.0.0.0:7000

# Join an existing cluster
devsper peer --listen 0.0.0.0:7001 --join 10.0.0.1:7000
```

### `inspect` — introspect a live run

```bash
devsper inspect <run-id>
```

## Global flags

| Flag | Description |
|------|-------------|
| `-v / --verbose` | Enable debug logging |

## Environment variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic provider key |
| `OPENAI_API_KEY` | OpenAI provider key |
| `OLLAMA_HOST` | Ollama base URL (default: `http://localhost:11434`) |
| `ZAI_API_KEY` | ZAI / GLM provider key |
| `ZAI_BASE_URL` | ZAI base URL (default: `https://api.z.ai/v1`) |

## Install

```bash
cargo install devsper-bin
```

Or build from source:

```bash
git clone https://github.com/devsper-com/runtime
cd runtime
cargo build --release -p devsper-bin
./target/release/devsper --help
```

## License

GPL-3.0-or-later — see [repository](https://github.com/devsper-com/runtime).
