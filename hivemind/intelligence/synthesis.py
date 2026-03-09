"""
v1.8: Cross-run synthesis — answer questions by querying across ALL memory (all runs).
"""

from collections.abc import Iterator
from datetime import datetime

from hivemind.knowledge.query import query_for_planning, format_planning_context, PlanningContext
from hivemind.memory.memory_index import MemoryIndex
from hivemind.memory.memory_types import MemoryRecord
from hivemind.knowledge.knowledge_graph import KnowledgeGraph
from hivemind.utils.models import generate


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _deduplicate_by_similarity(records: list[MemoryRecord], threshold: float = 0.95) -> list[MemoryRecord]:
    """Remove records with cosine similarity > threshold to an already-kept record."""
    if not records:
        return []
    out: list[MemoryRecord] = []
    for r in records:
        if r.embedding is None:
            out.append(r)
            continue
        keep = True
        for o in out:
            if o.embedding is None:
                continue
            if _cosine_sim(r.embedding, o.embedding) > threshold:
                keep = False
                break
        if keep:
            out.append(r)
    return out


def _short_run_id(run_id: str) -> str:
    """Short run id for citations (e.g. events_2025-03-09... -> 2025-03-09)."""
    if not run_id:
        return "unknown"
    if "_" in run_id:
        parts = run_id.split("_")
        if len(parts) >= 2:
            return parts[1][:12] if len(parts[1]) > 12 else parts[1]
    return run_id[:12] if len(run_id) > 12 else run_id


class CrossRunSynthesizer:
    """
    Answers questions by querying across ALL memory (all runs),
    not just the current session.
    """

    def __init__(
        self,
        memory_index: MemoryIndex,
        knowledge_graph: KnowledgeGraph | None,
        worker_model: str,
    ):
        self.memory_index = memory_index
        self.knowledge_graph = knowledge_graph
        self.worker_model = worker_model

    def synthesize(
        self,
        query: str,
        max_sources: int = 20,
        stream: bool = True,
        use_kg: bool = True,
        since: datetime | None = None,
    ) -> Iterator[str] | str:
        """
        1. Query memory_index across all runs (no run_id filter): top-20 by similarity
        2. Optionally query knowledge graph: query_for_planning(kg, query)
        3. Deduplicate: remove memory records with cosine similarity > 0.95 to each other
        4. Build synthesis prompt with all sources
        5. Stream LLM response (or return full string if stream=False)
        """
        memories = self.memory_index.query_across_runs(query, top_k=max_sources)
        if since is not None:
            memories = [m for m in memories if m.timestamp >= since]
        memories = _deduplicate_by_similarity(memories, threshold=0.95)
        memories = memories[:max_sources]

        kg_ctx: PlanningContext | None = None
        if use_kg and self.knowledge_graph is not None:
            kg_ctx = query_for_planning(self.knowledge_graph, query)

        prompt = self._build_synthesis_prompt(query, memories, kg_ctx)
        if stream:
            gen = generate(self.worker_model, prompt, stream=True)
            for chunk in gen:
                yield chunk
        else:
            return generate(self.worker_model, prompt, stream=False) or ""

    def _build_synthesis_prompt(
        self,
        query: str,
        memories: list[MemoryRecord],
        kg_ctx: PlanningContext | None,
    ) -> str:
        """Build system + user prompt for synthesis."""
        kg_block = ""
        if kg_ctx and (kg_ctx.relevant_concepts or kg_ctx.prior_findings or kg_ctx.related_methods):
            kg_block = "Knowledge Graph Facts:\n" + format_planning_context(kg_ctx) + "\n\n"
        unique_runs = list(dict.fromkeys(getattr(m, "run_id", "") or "" for m in memories))
        unique_runs = [r for r in unique_runs if r]
        memory_block = "\n".join(
            f"[run:{_short_run_id(getattr(m, 'run_id', ''))}] {(m.content or '')[:300]}"
            for m in memories
        )
        user = f"""Query: {query}

{kg_block}Memory Sources ({len(memories)} records across {len(unique_runs)} runs):
{memory_block}"""
        system = """You are synthesizing research findings across multiple past sessions.
Answer the query using ONLY the provided sources.
Cite sources as [run:RUN_ID_SHORT] inline.
If sources conflict, note the conflict explicitly.
Do not speculate beyond the sources."""
        return f"System:\n{system}\n\nUser:\n{user}"
