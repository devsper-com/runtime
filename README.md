<p align="center">
  <img src="https://raw.githubusercontent.com/devsper-com/runtime/refs/heads/main/branding/logo.svg" alt="devsper" width="120" height="140" style="background:#fff; padding:12px; border-radius:10px; filter:invert(1);" />
</p>

<h1 align="center">devsper</h1>
<p align="center"><strong>Distributed AI Swarm Runtime</strong></p>

<p align="center">
  <a href="https://pypi.org/project/devsper/"><img src="https://img.shields.io/pypi/v/devsper?label=PyPI" alt="PyPI"></a>
  <a href="https://www.gnu.org/licenses/gpl-3.0"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-green.svg" alt="Python 3.11+"></a>
  <a href="https://www.rust-lang.org/"><img src="https://img.shields.io/badge/powered%20by-Rust-orange.svg" alt="Powered by Rust"></a>
</p>

<p align="center">
  <em>Python CLI · Rust execution engine · distributed agent DAGs · keyring credentials · OpenTelemetry traces</em>
</p>

---

## Architecture

```
pip install devsper          # Python CLI (credentials, auth, eval, TUI)
       │
       ▼
devsper run workflow.devsper # Python injects credentials from keyring → env
       │
       ▼
devsper (Rust binary)        # DAG execution, LLM calls, OTEL spans
       │
       ▼
Providers: Anthropic · OpenAI · GitHub Models · ZAI · Azure OpenAI
           Azure Foundry · LiteLLM · Ollama
```

The Python package handles credentials, auth, eval, and TUI. The Rust binary handles workflow execution, scheduling, and LLM calls. Install both:

```bash
pip install devsper
cargo install devsper-bin    # or download from releases
```

---

## Quick start

**1. Install:**

```bash
pip install devsper
cargo install devsper-bin
```

**2. Set up credentials:**

```bash
# Store in OS keychain (macOS Keychain / Linux libsecret / Windows Credential Manager)
devsper credentials set anthropic
devsper credentials set openai

# GitHub Models — device flow (no API key needed, uses your GitHub account)
devsper auth github

# Azure OpenAI
devsper credentials set azure-openai    # prompts for api_key, endpoint, deployment

# Or set env vars directly (env always wins over keyring)
export ANTHROPIC_API_KEY=sk-...
```

**3. Write and run a workflow:**

```bash
cat > hello.devsper << 'EOF'
name = "hello"
model = "claude-sonnet-4-6"
workers = 2

[[tasks]]
id = "summarize"
prompt = "Explain swarm intelligence in one paragraph."
EOF

devsper run hello.devsper
```

---

## Credentials

API keys stay in your OS keychain — never in config files or shell history.

```bash
devsper credentials set <provider>      # interactive field prompts → keyring
devsper credentials list                # table: provider | fields | source
devsper credentials remove <provider>  # delete from keyring
devsper auth github                     # GitHub device flow → token → keyring
devsper auth status                     # what's authenticated and where
```

**Supported providers:**

| Provider | Command | Key env vars |
|---|---|---|
| Anthropic | `credentials set anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI | `credentials set openai` | `OPENAI_API_KEY` |
| GitHub Models | `auth github` | `GITHUB_TOKEN` |
| ZAI (z.ai) | `credentials set zai` | `ZAI_API_KEY`, `ZAI_BASE_URL` |
| Azure OpenAI | `credentials set azure-openai` | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |
| Azure Foundry | `credentials set azure-foundry` | `AZURE_FOUNDRY_API_KEY`, `AZURE_FOUNDRY_ENDPOINT`, `AZURE_FOUNDRY_DEPLOYMENT` |
| LiteLLM | `credentials set litellm` | `LITELLM_BASE_URL`, `LITELLM_API_KEY` |
| Ollama | `credentials set ollama` | `OLLAMA_HOST` |

Credentials set in environment variables always take priority over keyring.

### GitHub device flow

```bash
export DEVSPER_GITHUB_CLIENT_ID=<your-github-oauth-app-client-id>
devsper auth github
# → Opens: https://github.com/login/device/code
# → Enter code: XXXX-XXXX
# → Token stored in keyring automatically
```

Register a GitHub OAuth App at [github.com/settings/developers](https://github.com/settings/developers) to get a `client_id`. No client secret needed for device flow.

---

## Workflow format

```toml
# hello.devsper
name = "research"
model = "claude-sonnet-4-6"    # default model for all tasks
workers = 4

[[tasks]]
id = "outline"
prompt = "Create a research outline for: quantum computing in drug discovery"

[[tasks]]
id = "section_1"
prompt = "Write section 1: Background and motivation"
depends_on = ["outline"]
model = "gpt-4o"                # per-task model override

[[tasks]]
id = "section_2"
prompt = "Write section 2: Current approaches"
depends_on = ["outline"]

[[tasks]]
id = "conclusion"
prompt = "Write a conclusion synthesizing the above sections"
depends_on = ["section_1", "section_2"]
```

```bash
devsper run research.devsper
devsper run research.devsper --input "topic=quantum computing"
devsper compile research.devsper          # → research.bin (bytecode)
```

**Model prefixes by provider:**

| Prefix | Provider |
|---|---|
| `claude-*` | Anthropic |
| `gpt-*`, `o1*`, `o3*` | OpenAI |
| `github:<model>` | GitHub Models (e.g. `github:gpt-4o`) |
| `azure:<model>` | Azure OpenAI |
| `foundry:<model>` | Azure Foundry |
| `litellm:<model>` | LiteLLM proxy |
| `ollama:<model>` | Ollama |
| `zai:*`, `glm-*` | ZAI |

---

## Eval

Evaluate workflows against datasets with LLM-as-judge scoring:

```bash
pip install 'devsper[eval]'    # TruLens + OpenEvals

# Dataset: JSONL, one case per line
echo '{"input": "What is photosynthesis?", "expected": "plants convert light to energy"}' > cases.jsonl

devsper eval run workflow.devsper --dataset cases.jsonl --metrics relevance,correctness
devsper eval report --input eval_results.jsonl
```

Results written to `eval_results.jsonl`. TruLens dashboard automatically ingested when TruLens is installed.

---

## Observability

All LLM calls emit [OpenTelemetry](https://opentelemetry.io/) spans with `gen_ai.*` semantic conventions:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
devsper run workflow.devsper
# → spans exported: gen_ai.system, gen_ai.request.model, gen_ai.usage.input_tokens, etc.
```

Works with Jaeger, Grafana Tempo, Honeycomb, TruLens OTEL collector, or any OTLP-compatible backend. No-op if `OTEL_EXPORTER_OTLP_ENDPOINT` is not set.

---

## CLI reference

| Command | Description |
|---|---|
| `devsper run <file.devsper>` | Execute a workflow |
| `devsper compile <file.devsper>` | Compile to bytecode |
| `devsper peer --listen <addr>` | Start a cluster peer node |
| `devsper inspect <run-id>` | Inspect a running workflow |
| `devsper tui [run-id]` | Terminal UI (requires `devsper[tui]`) |
| `devsper credentials set <provider>` | Store credentials in keyring |
| `devsper credentials list` | Show configured providers |
| `devsper credentials remove <provider>` | Remove from keyring |
| `devsper auth github` | GitHub device flow login |
| `devsper auth status` | Show auth status for all providers |
| `devsper eval run <wf> --dataset <f>` | Batch eval against dataset |
| `devsper eval report` | Show eval results table |

---

## Optional extras

```bash
pip install 'devsper[tui]'     # Textual TUI
pip install 'devsper[eval]'    # TruLens + OpenEvals batch evaluation
```

---

## Distributed workers

```bash
# Start a cluster peer
devsper peer --listen 0.0.0.0:7000

# Join existing cluster
devsper peer --listen 0.0.0.0:7001 --join 192.168.1.10:7000

# Submit to cluster
devsper run workflow.devsper --cluster 192.168.1.10:7000
```

---

## How devsper compares

| | devsper | swarms | crewai | autogen |
|--|---------|--------|--------|---------|
| Rust execution engine | ✅ | ❌ | ❌ | ❌ |
| Distributed peer cluster | ✅ | ❌ | ❌ | ❌ |
| OS keychain credentials | ✅ | ❌ | ❌ | ❌ |
| GitHub Models device flow | ✅ | ❌ | ❌ | ❌ |
| OpenTelemetry traces | ✅ Native gen_ai.* spans | ❌ | ❌ | ❌ |
| LLM eval pipeline | ✅ TruLens + OpenEvals | ❌ | ❌ | ❌ |
| DAG-based scheduling | ✅ | ❌ | ❌ | ❌ |
| Compiled workflow format | ✅ .devsper bytecode | ❌ | ❌ | ❌ |
| 8 LLM providers | ✅ | ⚠️ Partial | ⚠️ Partial | ⚠️ Partial |

---

## Building from source

```bash
git clone https://github.com/devsper-com/runtime
cd runtime

# Build Rust binary
cargo build --release -p devsper-bin
# Binary at: target/release/devsper

# Install Python CLI (dev mode)
cd python
pip install -e .
```

---

## Documentation

Full docs: **[docs.devsper.com](https://docs.devsper.com)**

---

## License

**GPL-3.0-or-later** — see [LICENSE](LICENSE).
