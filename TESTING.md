# Manual Testing Guide

Tests that cannot be automated — require real LLM API keys and human judgement.

---

## Setup

### Option A — keyring (recommended)

The Python CLI stores credentials in the OS keychain and injects them as env vars before every Rust exec.

```bash
pip install 'devsper[tui]'   # or: pip install -e 'python/[tui]'

# Interactive credential setup — prompts for each field
devsper credentials set anthropic
devsper credentials set openai
devsper credentials set github
devsper credentials set zai
devsper credentials set azure-openai      # needs key + endpoint + deployment
devsper credentials set azure-foundry     # Azure AI Foundry (Anthropic Claude)
devsper credentials set litellm           # LiteLLM proxy (base_url + optional key)
devsper credentials set ollama            # host URL only

# Verify what's stored
devsper credentials list

# GitHub OAuth (device flow — no API key needed, tokens stored in keychain)
devsper auth github
devsper auth status
```

Once set, all `devsper run/compile/peer/inspect` calls automatically pick up credentials — no manual `export` needed.

### Option B — env vars (shell / CI)

```bash
# Build the Rust binary
cargo build -p devsper-bin --release
alias devsper="./target/release/devsper"

# Set at least one provider
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export ZAI_API_KEY="..."
export GITHUB_TOKEN="ghp_..."

# Azure OpenAI
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://your-resource.cognitiveservices.azure.com/openai/v1"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o"
export AZURE_OPENAI_API_VERSION="2025-04-01-preview"   # optional

# Azure AI Foundry (Anthropic Claude via Azure)
export AZURE_FOUNDRY_API_KEY="..."
export AZURE_FOUNDRY_ENDPOINT="https://your-resource.services.ai.azure.com/anthropic/v1/messages"
export AZURE_FOUNDRY_DEPLOYMENT="claude-opus-4-6-2"

# LiteLLM proxy
export LITELLM_BASE_URL="http://localhost:4000"
export LITELLM_API_KEY="..."   # optional

# Ollama
export OLLAMA_HOST="http://localhost:11434"   # default

# OTEL (optional — enables distributed tracing)
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
```

Without any key the CLI uses a mock provider (good for pipeline testing, not quality testing).

---

## 1. Pipeline smoke test (no API key needed)

Verify the full compile → run pipeline works:

```bash
# Parse and compile
devsper compile examples/research.devsper
devsper compile examples/code.devsper
devsper compile examples/general.devsper

# Run with mock provider
devsper run examples/general.devsper --input prompt="hello"
```

**Expected:**
- Each compile prints `Compiled: examples/<name>.devsper.bin`
- Run logs show: workflow loaded → executor started → all tasks complete → run complete
- WARN line: `No LLM provider keys found — using mock provider`
- No ERROR lines

**Unit tests:**

```bash
cargo test --workspace
# Expected: all tests pass, 0 failures
```

---

## 2. Research application

Tests the `search → analyze → synthesize` DAG with real LLMs.

```bash
devsper run examples/research.devsper --input topic="transformer attention mechanisms"
```

**What to verify:**
- Three tasks execute in correct order (search before analyze, both before synthesize)
- No task marked `Failed` in logs
- Run completes with `run complete` log line

**Quality check (human):**
- Does `search` return a plausible list of papers/resources?
- Does `analyze` identify real open problems?
- Does `synthesize` produce a coherent 400-600 word summary referencing earlier tasks?

**Stress variant:**
```bash
devsper run examples/research.devsper \
  --input topic="interpretability of large language models via sparse autoencoders"
```

---

## 3. Code application

Tests the `plan → implement → review` DAG.

```bash
devsper run examples/code.devsper \
  --input task="implement a thread-safe LRU cache in Rust with get and put methods"
```

**What to verify:**
- Plan task uses `claude-opus-4-7` (set in workflow), implement/review use default model
- All three tasks execute in order with no failures

**Quality check (human):**
- Does `plan` produce ≥3 concrete steps?
- Does `implement` produce compilable Rust code?
- Does `review` catch real issues (lock poisoning, edge cases)?

**Language override variant:**
```bash
devsper run examples/code.devsper \
  --input task="implement a rate limiter using the token bucket algorithm" \
  --input language="Python"
```

---

## 4. General / other applications

```bash
devsper run examples/general.devsper \
  --input prompt="Write a 1-page product brief for a CLI tool that runs AI workflows locally"

devsper run examples/general.devsper \
  --input prompt="Compare actor-model vs CSP concurrency for distributed AI systems"

devsper run examples/general.devsper \
  --input prompt="Suggest three improvements" \
  --input context="Rust runtime executing AI workflows as DAGs with parallel task execution."
```

**Expected:** single task completes, response coherent and on-topic.

---

## 5. Compile → run from bytecode

```bash
devsper compile examples/general.devsper --output /tmp/general.bin
devsper run /tmp/general.bin --input prompt="What is the capital of France?"
```

**Expected:** same behavior as running the source file directly.

---

## 6. CLI help and flags

```bash
devsper --help
devsper run --help
devsper compile --help
devsper peer --help
devsper credentials --help
devsper auth --help
devsper eval --help
```

**Expected:** no panics, all subcommands documented.

```bash
devsper -v run examples/general.devsper --input prompt="hello"
```

**Expected:** debug-level logs (provider routing, graph mutations, etc.).

---

## 7. Credentials and auth

```bash
# Set and list
devsper credentials set anthropic
devsper credentials list
# Expected: Anthropic row shows ✓ with masked key

# Remove
devsper credentials remove anthropic
devsper credentials list
# Expected: Anthropic row shows ✗

# GitHub OAuth device flow
devsper auth github
# Expected: prints device code + URL, polls until authorized, stores token

devsper auth status
# Expected: rich table showing each provider, status (✓/✗), and storage location
```

---

## 8. Eval

Requires `pip install 'devsper[eval]'` for TruLens scoring. Basic run works without it.

```bash
# Create a minimal JSONL dataset
echo '{"input": "what is 2+2?"}' > /tmp/eval_dataset.jsonl
echo '{"input": "capital of France?"}' >> /tmp/eval_dataset.jsonl

# Run eval
devsper eval run examples/general.devsper \
  --dataset /tmp/eval_dataset.jsonl \
  --output /tmp/eval_results.jsonl

# Expected: each case logged, results written to eval_results.jsonl

# Report
devsper eval report --input eval_results.jsonl
# Expected: table with inputs, outputs, latency, success rate

# With TruLens scoring (needs eval extra + OPENAI_API_KEY)
devsper eval run examples/general.devsper \
  --dataset /tmp/eval_dataset.jsonl \
  --metrics "relevance,coherence" \
  --score
```

---

## 9. OTEL tracing

```bash
# Start a local OTLP collector (e.g. Jaeger all-in-one)
docker run -p 4318:4318 -p 16686:16686 jaegertracing/all-in-one

export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
devsper run examples/research.devsper --input topic="test"
```

**Expected:**
- No OTEL-related errors in stderr
- Spans visible in Jaeger UI at http://localhost:16686 under service `devsper`
- `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` attributes present on LLM spans

---

## 10. Cluster peer (manual, two terminals)

```bash
# Terminal 1 — coordinator
devsper peer --listen 0.0.0.0:7000

# Terminal 2 — worker joining
devsper peer --listen 0.0.0.0:7001 --join 127.0.0.1:7000
```

**Expected:**
- Terminal 1: `Peer node started`, then `became coordinator`
- Terminal 2: `Peer node started`
- Both stay alive until Ctrl-C, no panics or ERROR logs

---

## 11. Error handling

```bash
# Missing required input (template literal passes through unchanged)
devsper run examples/research.devsper
# Expected: workflow loads, task executes with literal "{{topic}}" in prompt

# Non-existent file
devsper run does_not_exist.devsper
# Expected: error message about file not found, non-zero exit code

# Invalid workflow syntax
echo 'invalid lua {{{{' > /tmp/bad.devsper
devsper run /tmp/bad.devsper
# Expected: `Parse error:` message, non-zero exit code
```

---

## Known limitations (not tested)

- `--inspect-socket` TUI inspection: not yet wired
- `--cluster` remote submission: not yet wired
- `--embed` standalone binary: stub (compiles to bytecode)
- Input interpolation (`{{topic}}`) in prompts: compiler parses but runtime does not substitute yet
- Ollama provider: tested structurally, requires local Ollama instance for end-to-end
- `devsper eval` scoring with TruLens/OpenEvals: requires `devsper[eval]` extra and an OpenAI key for the LLM judge
- TUI (`devsper tui`): requires `devsper[tui]` extra
