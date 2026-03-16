"""
v1.8: Memory consolidation — cluster similar records, summarize clusters, archive originals.
"""

from dataclasses import dataclass

from devsper.memory.memory_store import MemoryStore
from devsper.memory.memory_index import MemoryIndex
from devsper.memory.memory_types import MemoryRecord, MemoryType
from devsper.memory.memory_store import generate_memory_id
from devsper.utils.models import generate


@dataclass
class ConsolidationReport:
    clusters_found: int
    clusters_consolidated: int
    records_archived: int
    records_created: int
    tokens_saved_estimate: int


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class MemoryConsolidator:
    """
    Clusters similar memory records, summarizes each cluster into one
    high-quality record, archives originals. Keeps agent context tight
    for long-running projects.
    """

    def __init__(self, min_cluster_size: int = 3):
        self.min_cluster_size = min_cluster_size

    async def _summarize_cluster(self, records: list[MemoryRecord], model: str) -> str:
        """Synthesize N related memory records into one comprehensive record. Max 300 words."""
        blocks = "\n\n".join((r.content or "")[:500] for r in records[:20])
        prompt = f"""Synthesize these {len(records)} related memory records into one comprehensive, information-dense record. Preserve all unique facts. Max 300 words.

Records:
{blocks}"""
        out = generate(model, prompt)
        return (out or "").strip()[:2000]

    async def consolidate(
        self,
        memory_store: MemoryStore,
        memory_index: MemoryIndex,
        worker_model: str,
        dry_run: bool = False,
    ) -> ConsolidationReport:
        """
        1. Load all memory records (include archived for clustering? No - only non-archived)
        2. Cluster by embedding similarity (AgglomerativeClustering, distance_threshold=0.25)
        3. For clusters with >= min_cluster_size records: generate summary
        4. Store summary as new MemoryRecord (type=semantic, tagged "consolidated")
        5. Archive originals: set archived=True
        6. Return report
        """
        try:
            from sklearn.cluster import AgglomerativeClustering
            import numpy as np
        except ImportError:
            raise ImportError(
                "Memory consolidation requires scikit-learn. Install with: pip install devsper[data]"
            ) from None

        records = memory_store.list_memory(limit=5000, include_archived=False)
        with_emb = [r for r in records if r.embedding is not None]
        if len(with_emb) < self.min_cluster_size:
            return ConsolidationReport(
                clusters_found=0,
                clusters_consolidated=0,
                records_archived=0,
                records_created=0,
                tokens_saved_estimate=0,
            )

        X = np.array(with_emb[0].embedding)
        for r in with_emb[1:]:
            X = np.vstack([X, r.embedding])
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=0.25,
            metric="cosine",
            linkage="average",
        )
        labels = clustering.fit_predict(X)
        unique_labels = set(labels)
        clusters_found = len(unique_labels)
        clusters_consolidated = 0
        records_archived = 0
        records_created = 0
        avg_tokens = 100

        for lab in unique_labels:
            indices = [i for i, l in enumerate(labels) if l == lab]
            cluster_records = [with_emb[i] for i in indices]
            if len(cluster_records) < self.min_cluster_size:
                continue
            clusters_consolidated += 1
            if dry_run:
                records_archived += len(cluster_records)
                records_created += 1
                continue
            summary_text = await self._summarize_cluster(cluster_records, worker_model)
            summary_record = MemoryRecord(
                id=generate_memory_id(),
                memory_type=MemoryType.SEMANTIC,
                content=summary_text,
                tags=["consolidated"],
                run_id="",
                archived=False,
            )
            summary_record = memory_index.ensure_embedding(summary_record)
            memory_store.store(summary_record)
            records_created += 1
            for r in cluster_records:
                memory_store.set_archived(r.id, True)
                records_archived += 1

        tokens_saved_estimate = records_archived * avg_tokens
        return ConsolidationReport(
            clusters_found=clusters_found,
            clusters_consolidated=clusters_consolidated,
            records_archived=records_archived,
            records_created=records_created,
            tokens_saved_estimate=tokens_saved_estimate,
        )
