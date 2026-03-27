# Agent identities

Named identities allow persistent persona, model, and memory namespace per agent.

## Config

```toml
[[agent_identities]]
name = "researcher"
persona = "You are a meticulous research specialist."
model = "claude-sonnet-4-20250514"
memory_namespace = "researcher_v1"
tools = ["research", "documents"]
max_memory_entries = 200
temperature = 0.3
```

Planner outputs can include assignment objects:

```json
{"task":"Find relevant papers","agent":"researcher"}
```
