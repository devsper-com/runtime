# Budget-aware execution

Budget controls let runs stop automatically when estimated spend is reached.

## Configuration

```toml
[budget]
limit_usd = 0.50
on_exceeded = "stop" # warn | stop | raise
alert_at_pct = 80
```

## Python API

```python
from devsper import Swarm

swarm = Swarm(budget_usd=0.50, budget_on_exceeded="stop")
result = swarm.run("Analyze repository risks")
print(result.budget)
```

## CLI

```bash
devsper budget <run_id>
```
