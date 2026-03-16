---
title: Installation
---

# Installation

This guide covers how to install devsper, configure API keys, and verify your setup.

## Prerequisites

- **Python 3.10 or later**. Check your version with `python --version`.
- **pip** (bundled with Python) or [uv](https://github.com/astral-sh/uv) for faster dependency resolution.

## Install from PyPI

The recommended way to install devsper:

```bash
pip install devsper
```

Or using uv:

```bash
uv pip install devsper
```

### Optional extras

devsper ships optional dependency groups for specialized features:

```bash
# Data science tools (scikit-learn for result consolidation)
pip install 'devsper[data]'

# Distributed mode (Redis and RPC dependencies)
pip install 'devsper[distributed]'

# Both extras at once
pip install 'devsper[data,distributed]'
```

## Development install

To work on devsper itself or run from the latest source:

```bash
git clone https://github.com/devsper/devsper.git
cd devsper
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

devsper needs credentials for at least one LLM provider. Supported providers include OpenAI, Anthropic, Gemini, Azure, and GitHub Models.

### Using the credential store (recommended)

devsper stores API keys in your OS keychain so they never appear in config files or shell history:

```bash
devsper credentials set openai
# You will be prompted to enter your API key securely
```

To list stored credentials:

```bash
devsper credentials list
```

### Using environment variables

Alternatively, export keys directly:

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

Environment variables take the highest priority and override any stored credentials.

### Configuration priority

devsper resolves configuration in this order (highest to lowest):

1. Environment variables
2. Project config (`./devsper.toml`)
3. User config (`~/.config/devsper/config.toml`)
4. Built-in defaults

## Verifying the installation

Run the built-in diagnostic command to confirm everything is working:

```bash
devsper doctor
```

This checks your Python version, installed dependencies, credential availability, and network connectivity to configured providers.

## Initializing a new project

To scaffold a new devsper project with a default `devsper.toml` config file:

```bash
devsper init
```

This creates a minimal configuration file in the current directory that you can customize. See the [Quickstart](/docs/getting-started/quickstart) for next steps.

## Next steps

- [Quickstart](/docs/getting-started/quickstart) -- run your first task
- [Key Concepts](/docs/getting-started/concepts) -- understand the architecture
- [Configuration](/docs/configuration) -- full config reference
