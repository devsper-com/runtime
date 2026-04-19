# Manual Testing Guide

Tests that cannot be automated — require real LLM API keys and human judgement.

---

## Setup

### Build

```bash
cargo build -p devsper-bin --release
alias devsper="./target/release/devsper"
```

### Set credentials (keychain — recommended)

```bash
devsper credentials set anthropic      # ANTHROPIC_API_KEY
devsper credentials set openai         # OPENAI_API_KEY
devsper credentials set github         # GITHUB_TOKEN (or: devsper auth github)
devsper credentials set zai            # ZAI_API_KEY + ZAI_BASE_URL
devsper credentials set azure-openai   # key + endpoint + deployment
devsper credentials set azure-foundry  # key + endpoint + deployment (Anthropic on Azure)
devsper credentials set litellm        # base_url + optional key
devsper credentials set ollama         # host (default: http://localhost:11434)

devsper credentials list               # verify what's stored
devsper auth status                    # show all providers: keychain / env / unset
```

### Set credentials (env — CI / quick test)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export GITHUB_TOKEN="ghp_..."
export ZAI_API_KEY="..."
export AZURE_OPENAI_API_KEY="..." AZURE_OPENAI_ENDPOINT="..." AZURE_OPENAI_DEPLOYMENT="..."
export AZURE_FOUNDRY_API_KEY="..." AZURE_FOUNDRY_ENDPOINT="..." AZURE_FOUNDRY_DEPLOYMENT="..."
export LITELLM_BASE_URL="http://localhost:4000"
export OLLAMA_HOST="http://localhost:11434"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"  # optional tracing
```

Without any key: mock provider (pipeline testing only).

---

## 1. Pipeline smoke test (no API key needed)

```bash
cargo test --workspace
# Expected: all pass, 0 failures

devsper compile examples/research.devsper
devsper compile examples/code.devsper
devsper compile examples/general.devsper
# Expected: Compiled: examples/<name>.devsper.bin

devsper run examples/general.devsper --input prompt="hello"
# Expected: workflow loaded → tasks complete → run complete
# WARN: "No LLM provider keys found — using mock provider"
```

---

## 2. CLI — run workflows

```bash
# Research DAG (search → analyze → synthesize)
devsper run examples/research.devsper --input topic="transformer attention mechanisms"

# Code DAG (plan → implement → review)
devsper run examples/code.devsper \
  --input task="implement a thread-safe LRU cache in Rust"

# General single-agent
devsper run examples/general.devsper \
  --input prompt="Compare actor-model vs CSP concurrency for distributed AI"
```

**Verify per workflow:**
- No `Failed` tasks in logs
- `run complete` at end
- Research: 3 tasks in order (search before analyze, both before synthesize)
- Code: plan uses `claude-opus-4-7`, implement/review use default model
- General: single task, coherent response

---

## 3. CLI — credentials and auth

```bash
devsper credentials set anthropic
devsper credentials list
# Row shows ✓

devsper credentials remove anthropic
devsper credentials list
# Row shows ✗

devsper auth github
# Prints device code + URL, polls until authorized, stores token

devsper auth status
# Table: all 8 providers, status, source (keychain/env/unset)
```

---

## 4. CLI — eval

```bash
echo '{"input": "what is 2+2?"}' > /tmp/eval.jsonl
echo '{"input": "capital of France?"}' >> /tmp/eval.jsonl

devsper eval run examples/general.devsper \
  --dataset /tmp/eval.jsonl \
  --output /tmp/eval_results.jsonl

devsper eval report --input /tmp/eval_results.jsonl
# Table: success rate, avg latency, per-case output preview
```

---

## 5. Python API (`import devsper`)

Requires a built or installed wheel. For local dev:

```bash
cd python && maturin develop --release
```

Then:

```bash
# Quickstart
python examples/quickstart.py

# Programmatic NodeSpecs
python examples/programmatic.py

# Concurrent async
python examples/async_example.py

# Coding agent
python examples/coding_agent.py
```

**Verify:**
- No import errors
- Results dict returned with node IDs as keys
- Async example runs 3 workflows concurrently, all complete

**Inline smoke test:**
```python
import devsper
r = devsper.run("examples/general.devsper", inputs={"prompt": "hello"})
assert isinstance(r, dict)
assert len(r) > 0
print("ok:", r)
```

---

## 6. Bytecode path

```bash
devsper compile examples/general.devsper --output /tmp/general.bin
devsper run /tmp/general.bin --input prompt="What is the capital of France?"
# Same behavior as running source directly
```

---

## 7. Cluster peer

```bash
# Terminal 1
devsper peer --listen 0.0.0.0:7000

# Terminal 2
devsper peer --listen 0.0.0.0:7001 --join 127.0.0.1:7000
```

**Expected:** coordinator elected, both peers alive, no panics or ERROR logs.

---

## 8. OTEL tracing

```bash
docker run -p 4318:4318 -p 16686:16686 jaegertracing/all-in-one
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"
devsper run examples/research.devsper --input topic="test"
```

**Expected:** spans visible in Jaeger at http://localhost:16686 under service `devsper`.
Attributes present: `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`.

---

## 9. Error handling

```bash
devsper run does_not_exist.devsper
# Expected: file not found error, non-zero exit

echo 'invalid lua {{{{' > /tmp/bad.devsper
devsper run /tmp/bad.devsper
# Expected: Parse error, non-zero exit

devsper --help && devsper run --help && devsper credentials --help && devsper eval --help
# Expected: no panics, all subcommands documented
```

---

## Known limitations

- `--inspect-socket` TUI inspection: not yet wired
- `--cluster` remote submission: not yet wired
- Input interpolation (`{{topic}}`) parsed but not substituted at runtime
- `devsper auth github` requires `DEVSPER_GITHUB_CLIENT_ID` env var (your OAuth App)
- Ollama: structurally tested, requires local instance for end-to-end
- Linux aarch64: no PyPI wheel — use `cargo install devsper-bin`
