# devsper

Self-evolving AI workflow engine — run `.devsper` workflows locally or at scale.

```bash
pip install devsper
devsper run workflow.devsper --input topic="transformers"
```

## Providers

Set any one key and `devsper` picks it up automatically:

| Provider | Env var |
|---|---|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| GitHub Models | `GITHUB_TOKEN` |
| ZAI / GLM | `ZAI_API_KEY` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` + `AZURE_OPENAI_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT` |
| Azure AI Foundry | `AZURE_FOUNDRY_API_KEY` + `AZURE_FOUNDRY_ENDPOINT` + `AZURE_FOUNDRY_DEPLOYMENT` |
| LiteLLM proxy | `LITELLM_BASE_URL` |
| Ollama | `OLLAMA_HOST` (default: `http://localhost:11434`) |

Or store credentials in the OS keychain:

```bash
devsper credentials set anthropic
devsper auth github        # device flow, no API key needed
devsper auth status        # show what's configured
```

## Commands

```
devsper run <workflow.devsper> [--input key=value ...]
devsper compile <workflow.devsper> [--output <file>]
devsper peer --listen 0.0.0.0:7000 [--join <addr>]
devsper inspect <run-id>
devsper tui                # interactive UI (pip install 'devsper[tui]')
devsper eval run           # batch eval (pip install 'devsper[eval]')
```

## Links

- [Docs](https://docs.devsper.com)
- [GitHub](https://github.com/devsper-com/runtime)
- [devsper.com](https://devsper.com)
