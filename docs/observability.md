# Observability

`devsper` emits structured run events and OpenTelemetry spans.

## Enable OTEL

```toml
[telemetry]
otel_enabled = true
otel_endpoint = "http://localhost:4317"
cost_tracking = true
```

Or with env:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

## Span hierarchy

- `swarm.run`
  - `planner.plan`
  - `scheduler.schedule`
  - `executor.execute`
    - `agent.call`
    - `tool.call`

## Local tracing

```bash
devsper trace <run_id>
```

## Grafana/Jaeger

Point `otel_endpoint` to your collector, then export to Grafana Tempo or Jaeger.
