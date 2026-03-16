---
title: Agents
---

# Agents

Agents are the core execution unit in devsper. Each agent is a **stateless LLM worker** that receives a single task, calls a language model, optionally runs tools in a loop, and returns a result. Agents do not maintain state between tasks — all persistent state lives in [memory](/docs/concepts/memory), the [knowledge graph](/docs/concepts/knowledge-graph), and the event log.

## Lifecycle

1. The executor assigns a task (description + optional dependency context) to an agent.
2. The agent sends the prompt to an LLM via the **provider router**.
3. If tools are enabled, the agent enters a **tool loop**: it parses tool calls from the LLM response, executes them through the tool runner, appends tool results to the conversation, and re-prompts the LLM. This repeats until the model produces a final answer.
4. The agent returns the result to the executor.

```text
Task ──> Agent ──> LLM call ──> [Tool loop] ──> Result
                      ^               |
                      └───────────────┘
```

## Provider Router

The provider router maps model names to the correct backend. Supported providers:

| Provider  | Example model            |
|-----------|--------------------------|
| OpenAI    | `gpt-4o`                 |
| Anthropic | `claude-sonnet-4-20250514`      |
| Gemini    | `gemini-2.0-flash`       |
| Azure     | `azure/gpt-4o`           |
| GitHub    | `github/gpt-4o`          |

Configure the default model and provider in `devsper.toml`:

```toml
[llm]
model = "gpt-4o"
provider = "openai"
```

The router handles API key resolution, retry logic, and rate-limit back-off so that agents are provider-agnostic.

## Tool Loop

When tools are enabled for a task, the agent iterates:

1. Parse tool-call blocks from the LLM response.
2. Dispatch each call to the tool runner (see [Tools](/docs/concepts/tools)).
3. Append tool results as assistant context.
4. Re-prompt the LLM with the updated conversation.

The loop terminates when the LLM responds without any tool calls or when a configured iteration limit is reached.

## Message Bus (v1.7+)

Agents running in the same swarm can share discoveries in real time. Any agent can broadcast a finding by including a line prefixed with `BROADCAST:` in its output:

```text
BROADCAST: Dataset X contains 12,000 labeled images covering all target classes.
```

Other agents receive these broadcasts in a **Shared Discoveries** section injected into their prompt. This enables cross-agent coordination without direct coupling.

## Prefetch (v1.7+)

For large swarms, the executor may **prefetch** memory snapshots and tool manifests before an agent starts. When prefetched data is available, the agent skips its own fetch step and uses the pre-warmed context, reducing startup latency.

## Critic (v1.7+)

For eligible roles (configurable per task), a **CriticAgent** evaluates the result after the primary agent finishes. The critic scores the output on relevance and completeness. If the score falls below the threshold, the executor allows **one retry** — the original agent re-executes with the critic's feedback appended to the prompt.

## Events

Agents emit structured events throughout their lifecycle. These events are written to the event log and can be consumed by plugins or the [TUI](/docs/tui).

| Event             | When emitted                        |
|-------------------|-------------------------------------|
| `agent_started`   | Agent process begins                |
| `task_started`    | Agent begins working on a task      |
| `tool_called`     | Agent invokes a tool                |
| `task_completed`  | Agent finishes a task               |
| `agent_finished`  | Agent process ends                  |

## State Model

Agents are intentionally stateless. Between tasks:

- **Memory** persists summaries and key findings (see [Memory](/docs/concepts/memory)).
- The **knowledge graph** stores extracted entities and relationships (see [Knowledge Graph](/docs/concepts/knowledge-graph)).
- The **event log** records every action for auditability.

This design allows the executor to schedule any agent onto any task without migration of internal state, which is critical for parallel and [distributed](/docs/distributed) execution.

## Next Steps

- [Tools](/docs/concepts/tools) — built-in and custom tool reference
- [Swarm Runtime](/docs/swarm_runtime) — how tasks are planned and parallelized
- [Workflows](/docs/concepts/workflows) — predefined multi-step pipelines
