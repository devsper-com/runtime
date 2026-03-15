---
title: Knowledge Graph
---

# Knowledge Graph

The knowledge graph (KG) is a persistent store of **entities and relationships** extracted from tool outputs, document pipelines, and task results. It gives agents and the planner structured context that goes beyond flat text memory, enabling richer reasoning about how concepts, datasets, methods, and documents relate to each other.

## Data Model

The graph consists of **nodes** and **edges**.

### Node Types

| Type       | Description                              |
|------------|------------------------------------------|
| `document` | A file, URL, or ingested resource        |
| `concept`  | A topic, technique, or domain term       |
| `dataset`  | A named dataset referenced in research   |
| `method`   | An algorithm, model, or procedure        |

### Edge Types

| Type         | Description                                   |
|--------------|-----------------------------------------------|
| `mentions`   | Source node references the target node         |
| `cites`      | Source document cites target document          |
| `related_to` | General semantic relationship between nodes    |

## Building the Graph

Nodes and edges are created from two sources:

1. **Tool outputs** — tools that fetch documents, parse PDFs, or query APIs emit structured metadata that the KG ingestion pipeline converts into nodes and edges.
2. **Document pipelines** — bulk ingestion jobs (e.g., `hivemind ingest ./papers/`) process files and populate the graph in batch.

## Auto-Extraction (v1.8+)

After each run, hivemind automatically extracts entities and relationships from task results and inserts them into the KG. This runs in the **background** and is non-blocking — agents are not delayed while extraction completes.

Enable or disable auto-extraction in `hivemind.toml`:

```toml
[knowledge]
auto_extract = true
```

## Planner Integration (v1.8+)

When `guide_planning` is enabled, the planner queries the KG before generating a DAG. If matching entities are found with confidence above `min_confidence`, their context is injected into the planning prompt. This helps the planner avoid redundant tasks and leverage prior findings.

```toml
[knowledge]
guide_planning = true
min_confidence = 0.6
auto_extract = true
```

## Configuration

All KG settings live under the `[knowledge]` section of `hivemind.toml`:

| Key              | Type    | Default | Description                                     |
|------------------|---------|---------|-------------------------------------------------|
| `guide_planning` | bool    | `false` | Inject KG context into planner prompts          |
| `min_confidence` | float   | `0.5`   | Minimum confidence to include a KG match        |
| `auto_extract`   | bool    | `false` | Extract entities from results after each run    |

## Persistence

The graph is serialized to JSON and stored at:

```text
<data_dir>/knowledge_graph.json
```

The default `data_dir` is `.hivemind/` in your project root. The file is updated after each extraction pass and can be checked into version control or shared across environments.

## Query Interface

The query module at `hivemind/knowledge/query.py` exposes two primary operations:

- **Entity search** — matches a query string against node labels using fuzzy matching, returning ranked results.
- **Relationship traversal** — given a node, walks 1-2 hops along edges and returns connected nodes and edge types.

### CLI Usage

```bash
# Search for entities matching a query
hivemind query "diffusion models"

# Example output:
# Entities:
#   [concept] Diffusion Models (confidence: 0.92)
#   [method]  Latent Diffusion (confidence: 0.87)
# Relationships:
#   Diffusion Models --related_to--> Score Matching
#   Latent Diffusion --mentions--> ImageNet-256
# Documents:
#   doc_0042, doc_0078
```

## Integration with Memory

The KG complements the [memory](/docs/concepts/memory) system. A typical integration pattern:

1. A task completes and its summary is stored in memory with tags.
2. Auto-extraction pulls entities and relationships from the same result into the KG.
3. On a later run, the planner retrieves tagged memory summaries **and** KG context, giving agents both narrative and structural knowledge.

## Diagnostics

Run `hivemind doctor` to inspect the health of the knowledge graph:

```bash
hivemind doctor
# Knowledge Graph
#   Nodes: 342
#   Edges: 587
#   Last updated: 2026-03-12T14:22:01Z
```

## Next Steps

- [Memory](/docs/concepts/memory) — persistent text memory and tagging
- [Agents](/docs/concepts/agents) — how agents consume KG context
- [CLI Reference](/docs/cli) — full list of CLI commands
