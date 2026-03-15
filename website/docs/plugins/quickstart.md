---
title: Plugin Quickstart
---

# Plugin Quickstart

Build and install a hivemind plugin in 5 minutes. By the end, you will have a custom tool available in the hivemind runtime.

## Prerequisites

- Python 3.10+
- hivemind installed: `pip install hivemind-ai`

## Step 1: Create the Project

```bash
mkdir hivemind-plugin-wordcount
cd hivemind-plugin-wordcount
mkdir wordcount_plugin
touch wordcount_plugin/__init__.py
```

## Step 2: Write `pyproject.toml`

Create `pyproject.toml` in the project root:

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "hivemind-plugin-wordcount"
version = "0.1.0"
description = "A word count tool for hivemind"
requires-python = ">=3.10"
dependencies = ["hivemind-ai"]

[project.entry-points."hivemind.plugins"]
wordcount = "wordcount_plugin:register_tools"
```

The entry point under `hivemind.plugins` tells hivemind how to discover your plugin. The value `"wordcount_plugin:register_tools"` points to the `register_tools` function in `wordcount_plugin/__init__.py`.

## Step 3: Implement the Tool

Edit `wordcount_plugin/__init__.py`:

```python
from hivemind.tools.base import Tool
from hivemind.tools.registry import register


class WordCountTool(Tool):
    name = "word_count"
    description = "Count the number of words in a given text string."
    input_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The text to count words in"
            }
        },
        "required": ["text"]
    }

    def run(self, **kwargs) -> str:
        text = kwargs["text"]
        count = len(text.split())
        return f"Word count: {count}"


def register_tools():
    register(WordCountTool())
```

Key points:

- Subclass `Tool` from `hivemind.tools.base`.
- Define `name`, `description`, and `input_schema` (JSON Schema).
- Implement `run(**kwargs) -> str`. The method receives keyword arguments matching your schema properties and must return a string.
- Call `register()` in your entry point function.

## Step 4: Install Locally

From the project root:

```bash
pip install -e .
```

The `-e` flag installs in editable mode so you can modify your code without reinstalling.

## Step 5: Verify

Run the hivemind diagnostic command:

```bash
hivemind doctor
```

You should see `wordcount` listed under loaded plugins, and `word_count` listed as a registered tool.

## Step 6: Use It

Your tool is now available to the hivemind runtime. When the swarm encounters a task that requires counting words, it can select `word_count` automatically via smart tool selection.

You can also test the tool directly in Python:

```python
from wordcount_plugin import WordCountTool

tool = WordCountTool()
result = tool.run(text="hivemind makes AI tool development simple")
print(result)  # Word count: 6
```

## Project Structure

Your final project should look like this:

```
hivemind-plugin-wordcount/
  pyproject.toml
  wordcount_plugin/
    __init__.py
```

## Next Steps

- [Plugin Examples](/docs/plugins/examples) -- more complete examples including API integrations and file processing.
- [Tool Reference](/docs/plugins/tool-reference) -- browse the built-in tool categories for inspiration.
- [Publishing Plugins](/docs/plugins/publishing) -- share your plugin on PyPI or the hivemind registry.
- [Troubleshooting](/docs/plugins/troubleshooting) -- solutions for common issues.
