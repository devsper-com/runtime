# Packaging

Export reusable deployable agent packages as `.devsper` archives.

## Export

```bash
devsper export --name my-research-agent --out ./dist
```

Produces:

- `manifest.json`
- `devsper.toml`
- `workflow.devsper.toml` (if present)
- `requirements.txt`
- `README.md`
- `examples/`

## Run package

```bash
devsper run-package ./dist/my-research-agent.devsper "Your task here"
```
