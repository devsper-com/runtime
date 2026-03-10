# Testing the v2 LLM Router and MCP

Quick ways to verify the **2.0 LLM Router** and **MCP** integration.

---

## 1. MCP

### List and test (no run required)

From the project root (where `hivemind.toml` can live):

```bash
# List configured MCP servers and tool counts
hivemind mcp list

# Test a specific server (name must match [[mcp.servers]] entry)
hivemind mcp test filesystem
```

### Add an MCP server

```bash
hivemind mcp add
```

Then follow prompts (e.g. name `filesystem`, transport `stdio`, command `npx -y @modelcontextprotocol/server-filesystem /tmp`). This appends to `hivemind.toml`.

### Minimal `hivemind.toml` for MCP

```toml
[mcp]

[[mcp.servers]]
name = "filesystem"
transport = "stdio"
command = ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

### Run a task that can use MCP tools

After at least one MCP server is configured and listed by `hivemind mcp list`, run a task that uses tools (e.g. research/code). The agent will see MCP tools in the registry and can call them:

```bash
hivemind run "List files in /tmp and summarize what you see"
```

Use a model that supports tools (e.g. set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`; with no keys the mock model is used and tool behavior is limited).

---

## 2. v2 LLM Router

The v2 router is used for **non-streaming** `generate()` when at least one backend is registered (env or config). With **no** API keys and **no** Ollama/vLLM/custom enabled, the legacy router is used (mock provider).

### A. With an API key (OpenAI / Anthropic / etc.)

```bash
export OPENAI_API_KEY="sk-..."
hivemind run "Say hello in one sentence"
```

- If the v2 router is built (OpenAI backend registered), the request goes through `LLMRouter` and the OpenAI backend.
- You can set `HIVEMIND_PLANNER_MODEL` / `HIVEMIND_WORKER_MODEL` to force a provider, e.g. `openai:gpt-4o-mini`.

### B. With Ollama (no API key)

1. Start Ollama and pull a model, e.g. `ollama run llama3`.
2. Enable Ollama in config. In `hivemind.toml`:

```toml
[providers.ollama]
enabled = true
base_url = "http://localhost:11434"
```

3. Run with the `ollama:` prefix:

```bash
# Use explicit provider:model so the v2 router selects Ollama
HIVEMIND_WORKER_MODEL=ollama:llama3 HIVEMIND_PLANNER_MODEL=ollama:llama3 hivemind run "Say hello"
```

Or set in TOML:

```toml
[models]
planner = "ollama:llama3"
worker = "ollama:llama3"
```

### C. Quick script: v2 router only

Run this from the repo root (with at least one backend available: e.g. `OPENAI_API_KEY` set or Ollama enabled and running):

```bash
python scripts/test_v2_router.py
```

(See `scripts/test_v2_router.py` below.)

---

## 3. MCP + v2 router together

1. Configure MCP (e.g. `hivemind mcp add` or add `[[mcp.servers]]` to `hivemind.toml`).
2. Configure a real model via env or TOML (OpenAI, Ollama, etc.) so the v2 router is used.
3. Run a task that can use tools:

```bash
export OPENAI_API_KEY="sk-..."
hivemind run "Use the filesystem tool to list the contents of /tmp and summarize in one line"
```

This exercises: v2 router for LLM calls + MCP tools in the agent loop.

---

## 4. Fallback (optional)

To test provider fallback, set a fallback order and force a model that might fail first:

```toml
[providers.fallback_order]
order = ["openai", "anthropic"]
```

Then use a model like `openai:gpt-4o`; if the OpenAI call fails, the router will try Anthropic and emit a `PROVIDER_FALLBACK` event (visible in events JSONL for the run).
