"""Plan a swarm-based literature review: assign document subsets and themes to batches."""

import json
import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register

STOP = frozenset("a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that it its".split())


class SwarmLiteratureReviewTool(Tool):
    """
    Plan a literature review for a swarm: split documents into batches and suggest theme keywords per batch.
    Accepts raw text list (e.g. from prior extraction); does not read files.
    """

    name = "swarm_literature_review"
    description = "Plan swarm-based literature review: batch assignments and theme keywords per batch."
    input_schema = {
        "type": "object",
        "properties": {
            "texts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Document texts or abstracts (one per item)",
            },
            "batch_size": {"type": "integer", "description": "Texts per batch (default 3)"},
            "top_keywords_per_batch": {"type": "integer", "description": "Theme keywords per batch (default 5)"},
        },
        "required": ["texts"],
    }

    def run(self, **kwargs) -> str:
        texts = kwargs.get("texts")
        batch_size = kwargs.get("batch_size", 3)
        top_k = kwargs.get("top_keywords_per_batch", 5)
        if not texts or not isinstance(texts, list):
            return "Error: texts must be a non-empty list of strings"
        if not isinstance(batch_size, int) or batch_size < 1:
            batch_size = 3
        if not isinstance(top_k, int) or top_k < 1:
            top_k = 5
        batches = []
        for i in range(0, len(texts), batch_size):
            batch_texts = [t for t in texts[i : i + batch_size] if isinstance(t, str) and t.strip()]
            combined = " ".join(batch_texts).lower()
            words = [w for w in re.findall(r"[a-z]+", combined) if len(w) >= 4 and w not in STOP]
            from collections import Counter

            keywords = [w for w, _ in Counter(words).most_common(top_k)]
            batches.append({"batch_index": len(batches), "num_docs": len(batch_texts), "theme_keywords": keywords})
        result = {"total_documents": len(texts), "batch_size": batch_size, "batches": batches}
        return json.dumps(result, indent=2)


register(SwarmLiteratureReviewTool())
