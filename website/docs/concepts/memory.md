---
title: Memory
---

# Memory System

## Memory Types

The system supports four **memory types** for routing and indexing:

| Type | Use |
|------|-----|
| **Episodic** | Event-like, experience-based context (e.g. "what we did in this session"). |
| **Semantic** | Factual or conceptual knowledge (e.g. summaries, concepts, dataset descriptions). |
| **Research** | Literature, papers, citations, findings. |
| **Artifact** | Code, outputs, or structured artifacts (e.g. codebase summaries, reports). |

Each stored record has: `id`, `memory_type`, `timestamp`, `source_task`, `content`, `tags`, optional `embedding`, and `run_id` and `archived`.

## Memory Store

- **Backend:** SQLite (e.g. `.devsper/memory.db` or path from config).
- **Operations:** `store(record)`, `retrieve(memory_id)`, `list_memory(limit=...)`, `delete(memory_id)`.

## Embedding Search

- **MemoryIndex** maintains optional embeddings on records.
- **query_memory(text, top_k):** Embeds the query text, scores stored records by cosine similarity, returns top-k.
- **query_across_runs(text, top_k):** Same over all runs; optional `run_id_filter`.

## Memory Router

- **get_relevant_memory(task_description):** Uses the index to return top-k memories by similarity.
- **get_memory_context(task_description):** Formats those memories as a string block for injection into the agent prompt.

## Consolidation

Clusters records by embedding similarity, summarizes each cluster with an LLM, stores one new record per cluster, and marks originals as archived.

```bash
devsper memory consolidate [--dry-run] [--min-cluster-size 3]
```
