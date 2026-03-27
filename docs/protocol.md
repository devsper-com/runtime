# Polyglot protocol

The runtime supports a language-agnostic HTTP protocol for remote agents.

## Endpoints

- `GET /health`
- `GET /agent`
- `POST /agent/execute`

## Request

```json
{
  "task_id": "uuid",
  "run_id": "uuid",
  "task": "Task description",
  "context": {
    "memory": [],
    "prior_outputs": {},
    "tools_available": []
  },
  "config": {
    "model": "gpt-4o-mini",
    "max_tokens": 4096,
    "temperature": 0.7
  },
  "budget_remaining_usd": 0.5
}
```

## Response

```json
{
  "task_id": "uuid",
  "output": "Agent output",
  "tool_calls": [],
  "tokens": {"prompt": 0, "completion": 0},
  "cost_usd": 0.0,
  "duration_ms": 10,
  "error": null
}
```

## Start server

```bash
devsper serve --host 0.0.0.0 --port 8080
```
