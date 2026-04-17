# Manual Testing Guide

Tests that cannot be automated — require real LLM API keys and human judgement.

## Setup

```bash
# Build the CLI
cargo build -p devsper-bin --release
alias devsper="./target/release/devsper"

# Set at least one provider key
export ANTHROPIC_API_KEY="sk-ant-..."
# or
export OPENAI_API_KEY="sk-..."
# or
export ZAI_API_KEY="..."
```

Without a key, the CLI runs with a mock provider (good for pipeline testing, not for quality testing).

---

## 1. Pipeline smoke test (no API key needed)

Verify the full compile → run pipeline works:

```bash
# Parse and compile
devsper compile examples/research.devsper
devsper compile examples/code.devsper
devsper compile examples/general.devsper

# Run with mock provider (no API key)
devsper run examples/general.devsper --input prompt="hello"
```

**Expected:**
- Each compile prints `Compiled: examples/<name>.devsper.bin`
- Run logs show: workflow loaded → executor started → all tasks complete → run complete
- WARN line: `No LLM provider keys found — using mock provider`
- No ERROR lines

**Also run the unit tests:**

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
- Three tasks execute in correct order (search finishes before analyze, both before synthesize)
- No task marked `Failed` in logs
- Run completes with `run complete` log line

**Quality check (human):**
- Does `search` return a plausible list of papers/resources?
- Does `analyze` identify real open problems in the field?
- Does `synthesize` produce a coherent 400-600 word summary?
- Does the summary reference findings from earlier tasks?

**Stress variant** — longer topic:
```bash
devsper run examples/research.devsper --input topic="interpretability of large language models via sparse autoencoders"
```

---

## 3. Code application

Tests the `plan → implement → review` DAG with real LLMs.

```bash
devsper run examples/code.devsper \
  --input task="implement a thread-safe LRU cache in Rust with get and put methods"
```

**What to verify:**
- Plan task uses `claude-opus-4-7` (set in workflow), implement/review use default model
- All three tasks execute in order with no failures
- Run completes cleanly

**Quality check (human):**
- Does `plan` break the task into ≥3 concrete steps?
- Does `implement` produce compilable Rust code?
- Does `review` catch any real issues (e.g. lock poisoning, missing edge cases)?

**Variant with language override:**
```bash
devsper run examples/code.devsper \
  --input task="implement a rate limiter using the token bucket algorithm" \
  --input language="Python"
```

---

## 4. General / other applications

Single-agent open-ended tasks.

```bash
# Document drafting
devsper run examples/general.devsper \
  --input prompt="Write a 1-page product brief for a CLI tool that runs AI workflows locally"

# Analysis
devsper run examples/general.devsper \
  --input prompt="Compare the tradeoffs of actor-model vs CSP concurrency patterns for distributed AI systems"

# With context
devsper run examples/general.devsper \
  --input prompt="Suggest three improvements" \
  --input context="We have a Rust runtime that executes AI workflows as DAGs. Tasks run in parallel when their dependencies are met. "
```

**What to verify:**
- Single task completes without error
- Response is coherent and on-topic

---

## 5. Compile → run from bytecode

Verify the bytecode path works end-to-end:

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
```

**Expected:** no panics, all subcommands documented.

```bash
devsper -v run examples/general.devsper --input prompt="hello"
```

**Expected:** debug-level logs appear (provider routing, graph mutations, etc.)

---

## 7. Cluster peer (manual, two terminals)

```bash
# Terminal 1 — coordinator
devsper peer --listen 0.0.0.0:7000

# Terminal 2 — worker joining
devsper peer --listen 0.0.0.0:7001 --join 127.0.0.1:7000
```

**Expected:**
- Terminal 1: logs `Peer node started`, then `became coordinator`
- Terminal 2: logs `Peer node started`
- Both stay alive until Ctrl-C
- No panics or ERROR logs

---

## 8. Error handling

```bash
# Missing required input
devsper run examples/research.devsper
```
**Expected:** workflow loads (topic input is required but not validated at runtime yet — task will execute with `{{topic}}` literal).

```bash
# Non-existent file
devsper run does_not_exist.devsper
```
**Expected:** error message about file not found, non-zero exit code.

```bash
# Invalid workflow syntax
echo 'invalid lua {{{{' > /tmp/bad.devsper
devsper run /tmp/bad.devsper
```
**Expected:** `Parse error:` message, non-zero exit code.

---

## Known limitations (not tested)

- `--inspect-socket` TUI inspection: not yet wired
- `--cluster` remote submission: not yet wired  
- `--embed` standalone binary: stub (compiles to bytecode)
- Input interpolation (`{{topic}}`) in prompts: compiler parses but runtime does not substitute yet
- Ollama provider: tested structurally but requires local Ollama instance to verify end-to-end
