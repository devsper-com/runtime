---
title: Installation
---

# Installation

This guide covers how to install hivemind, configure API keys, and verify your setup.

## Prerequisites

- **Python 3.10 or later**. Check your version with `python --version`.
- **pip** (bundled with Python) or [uv](https://github.com/astral-sh/uv) for faster dependency resolution.

## Install from PyPI

The recommended way to install hivemind:

```bash
pip install hivemind-ai
```

Or using uv:

```bash
uv pip install hivemind-ai
```

### Optional extras

hivemind ships optional dependency groups for specialized features:

```bash
# Data science tools (scikit-learn for result consolidation)
pip install 'hivemind-ai[data]'

# Distributed mode (Redis and RPC dependencies)
pip install 'hivemind-ai[distributed]'

# Both extras at once
pip install 'hivemind-ai[data,distributed]'
```

## Development install

To work on hivemind itself or run from the latest source:

```bash
git clone https://github.com/hivemind-ai/hivemind.git
cd hivemind
```

Then install in editable mode using uv (preferred):

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Setting up API keys

hivemind needs credentials for at least one LLM provider. Supported providers include OpenAI, Anthropic, Gemini, Azure, and GitHub Models.

### Using the credential store (recommended)

hivemind stores API keys in your OS keychain so they never appear in config files or shell history:

```bash
hivemind credentials set openai
# You will be prompted to enter your API key securely
```

To list stored credentials:

```bash
hivemind credentials list
```

### Using environment variables

Alternatively, export keys directly:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

Environment variables take the highest priority and override any stored credentials.

### Configuration priority

hivemind resolves configuration in this order (highest to lowest):

1. Environment variables
2. Project config (`./hivemind.toml`)
3. User config (`~/.config/hivemind/config.toml`)
4. Built-in defaults

## Verifying the installation

Run the built-in diagnostic command to confirm everything is working:

```bash
hivemind doctor
```

This checks your Python version, installed dependencies, credential availability, and network connectivity to configured providers.

## Initializing a new project

To scaffold a new hivemind project with a default `hivemind.toml` config file:

```bash
hivemind init
```

This creates a minimal configuration file in the current directory that you can customize. See the [Quickstart](/docs/getting-started/quickstart) for next steps.

## Next steps

- [Quickstart](/docs/getting-started/quickstart) -- run your first task
- [Key Concepts](/docs/getting-started/concepts) -- understand the architecture
- [Configuration](/docs/configuration) -- full config reference
