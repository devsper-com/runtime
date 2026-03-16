---
title: Tool Reference
---

# Tool Reference

devsper ships with 120+ built-in tools organized into ten categories. This page provides an overview of each category and its key tools. For a full listing, run `devsper doctor` or call `list_tools()` at runtime.

## Tool Architecture

Every tool is stateless and defined by three properties:

- **name** -- unique identifier used for invocation.
- **description** -- natural language summary used by smart tool selection.
- **input_schema** -- JSON Schema defining the tool's expected parameters.

Tools implement a single method: `run(**kwargs) -> str`.

## Smart Tool Selection

When `top_k` is configured in the `[tools]` section, devsper uses semantic matching to select the most relevant tools for a given task rather than loading all tools into context:

```toml
[tools]
top_k = 10
```

Set `top_k = 0` to disable smart selection and load all enabled tools.

## Categories

### Research

Tools for literature review and information gathering.

- `arxiv_search` -- search arXiv for papers by query, author, or topic.
- `web_search` -- general-purpose web search with result extraction.
- `literature_review` -- synthesize findings across multiple papers.
- `citation_graph` -- build and traverse citation relationships.
- `topic_extraction` -- identify key topics from a body of text.

### Coding

Tools for codebase analysis and code generation.

- `codebase_indexer` -- index a repository for semantic code search.
- `dependency_graph` -- map import and dependency relationships.
- `architecture_analyzer` -- infer high-level architecture from source code.
- `refactor_candidates` -- identify code that would benefit from refactoring.
- `run_python` -- execute Python code in a sandboxed environment.
- `lint` -- run linting checks against source files.
- `generate_tests` -- produce unit tests for a given function or module.

### Data Science

Tools for dataset analysis and statistical exploration.

- `dataset_profile` -- generate summary statistics and metadata for a dataset.
- `outlier_detection` -- flag anomalous values using configurable methods.
- `correlation` -- compute pairwise correlation matrices.
- `distribution_report` -- characterize the distribution of numeric columns.
- `feature_importance` -- rank features by predictive relevance.

### Documents

Tools for document processing and extraction.

- `docproc_extraction` -- extract structured content from PDFs and office documents.
- `knowledge_graph` -- build entity-relationship graphs from unstructured text.
- `timeline_extraction` -- identify and order events mentioned in documents.
- `summarize` -- produce concise summaries of long-form content.
- `convert_to_markdown` -- convert various document formats to Markdown.

### Experiments

Tools for running and analyzing experiments.

- `grid_search` -- execute parameter grid searches over a function.
- `swarm_experiment_runner` -- orchestrate multi-agent experiment runs.
- `monte_carlo` -- run Monte Carlo simulations with configurable parameters.
- `statistical_tests` -- perform hypothesis tests (t-test, chi-square, ANOVA, etc.).
- `result_comparator` -- compare results across experiment runs.

### Memory

Tools for persistent key-value storage across tasks.

- `store` -- save a value under a named key.
- `list` -- list all stored keys, optionally filtered by prefix.
- `search` -- search stored values by content or metadata.
- `summarize_memory` -- summarize stored entries for a given key range.
- `tag` -- attach tags to stored entries for organization.
- `delete` -- remove a stored entry by key.

### Filesystem

Tools for local file and directory operations.

- `read_file` -- read the contents of a file.
- `write_file` -- write content to a file, creating it if needed.
- `list_directory` -- list files and subdirectories at a given path.
- `search_files` -- search for files matching a name or glob pattern.
- `file_metadata` -- retrieve size, modification time, and other metadata.

### System

Tools for interacting with the operating system.

- `run_shell_command` -- execute a shell command and capture output.
- `env_vars` -- read or list environment variables.
- `disk_usage` -- report disk space utilization.
- `cpu_usage` -- report current CPU utilization.
- `memory_usage` -- report system memory statistics.

### Knowledge

Tools for building structured knowledge from unstructured sources.

- `document_topic_extractor` -- extract topics with confidence scores.
- `citation_graph_builder` -- construct citation graphs from reference lists.
- `knowledge_graph_extractor` -- extract entities and relationships into a graph.
- `timeline_extractor` -- parse temporal references into ordered events.

### Flagship

Composite tools that orchestrate multiple steps for complex workflows.

- `docproc_corpus_pipeline` -- end-to-end pipeline for processing document corpora.
- `research_graph_builder` -- build a connected research knowledge graph from papers.
- `repository_semantic_map` -- generate a semantic map of an entire code repository.
- `distributed_document_analysis` -- analyze large document sets using distributed swarm agents.

## Configuration

Enable or disable categories in your devsper config:

```toml
[tools]
enabled = ["research", "coding", "data_science", "filesystem"]
top_k = 15
```

When `enabled` is omitted, all categories are active by default.

## Discovering Tools at Runtime

```python
from devsper.tools.registry import list_tools

for tool in list_tools():
    print(f"{tool.name}: {tool.description}")
```

## Further Reading

- [Plugin Quickstart](/docs/plugins/quickstart) -- create your own tools.
- [Plugin Examples](/docs/plugins/examples) -- full plugin code samples.
- [Publishing Plugins](/docs/plugins/publishing) -- share your tools with the community.
