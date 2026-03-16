# Memory System

## Memory Types

The system supports four **memory types** for routing and indexing:

| Type | Use |
|------|-----|
| **Episodic** | Event-like, experience-based context (e.g. “what we did in this session”). |
| **Semantic** | Factual or conceptual knowledge (e.g. summaries, concepts, dataset descriptions). |
| **Research** | Literature, papers, citations, findings. |
| **Artifact** | Code, outputs, or structured artifacts (e.g. codebase summaries, reports). |

Each stored record has: `id`, `memory_type`, `timestamp`, `source_task`, `content`, `tags`, and optional `embedding`.

## Memory Store

- **Backend:** SQLite (e.g. `.devsper/memory.db` or path from config).
- **Operations:** `store(record)`, `retrieve(memory_id)`, `list_memory(limit=…)`, `delete(memory_id)`.
- **Default instance:** `get_default_store()` uses the configured data directory.

Records are serialized with tags as a comma-separated string and embedding as JSON; the store handles schema creation and indexes on type and timestamp.

## Memory Retrieval

- **By ID:** `store.retrieve(memory_id)` returns one `MemoryRecord` or `None`.
- **List:** `store.list_memory(limit=N)` returns the most recent records (e.g. by timestamp).

## Embedding Search

- **MemoryIndex** maintains optional embeddings on records.
- **ensure_embedding(record):** Computes and attaches an embedding if missing (uses the project’s embedding function).
- **query_memory(text, top_k):** Embeds the query text, scores stored records by cosine similarity to the query embedding, and returns the top-k records. Records without embeddings are skipped for ranking (or a fallback like “latest by timestamp” can be used if none have embeddings).

This enables **semantic retrieval**: e.g. “analyze diffusion model papers” can pull in research and semantic memories about diffusion models.

## Knowledge Graph Integration

- The **knowledge graph** builds nodes (documents, concepts, datasets, methods) and edges (mentions, cites, related_to) from content (e.g. from tool outputs or document pipelines).
- Memory and the knowledge graph can be used together: store summaries or findings in memory with appropriate type/tags, and optionally feed knowledge-graph context into the agent or into downstream tools (e.g. document intelligence, research pipelines).

## Memory Router

- **Role:** Decide which memories are relevant to a task and format them for the agent.
- **get_relevant_memory(task_description):** Uses the index to return top-k memories by similarity to the task description.
- **get_memory_context(task_description):** Formats those memories as a string block (e.g. “RELEVANT MEMORY …”) for injection into the agent prompt.

The swarm (or agent) typically passes a `MemoryRouter` into the `Swarm`/`Agent` so each task gets relevant prior context without loading the full store.

## Summarization (v1)

- **Module:** `devsper.memory.summarizer`
- **summarize_extractive(records, max_chars):** Concatenates record contents up to a character limit (no LLM).
- **summarize_with_llm(records, model_name):** Uses an LLM to produce a short summary of the records; falls back to extractive on failure.
- **summarize(records, use_llm=False):** Single entry point; set `use_llm=True` for LLM summarization.

Useful for condensing many memories into a single context block or for namespace-level summaries.

## Namespaces (v1)

- **Module:** `devsper.memory.namespaces`
- **Concept:** Memories can be tagged with a namespace (e.g. `research_memory`, `coding_memory`, `dataset_memory`) using a tag prefix `ns:<namespace>`.
- **Helpers:** `add_namespace(record, namespace)`, `record_namespace(record)`, `filter_by_namespace(records, namespace)`.
- **Constants:** `RESEARCH_MEMORY`, `CODING_MEMORY`, `DATASET_MEMORY`.

The TUI memory view and any custom UI can filter by namespace when loading from the store.

## Scoring (v1)

- **Module:** `devsper.memory.scoring`
- **recency_score(record):** Newer memories score higher (exponential decay).
- **importance_score(record):** Heuristic based on content length and tag count.
- **score_and_sort(records, similarity_scores=None):** Combines similarity (e.g. from embedding search), recency, and importance to rank and sort records. Use this to re-rank results from the memory index before returning to the agent or UI.
