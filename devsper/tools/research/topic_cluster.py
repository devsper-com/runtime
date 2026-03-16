"""Simple topic clustering by common words across titles/texts."""

import re
from collections import Counter

from devsper.tools.base import Tool
from devsper.tools.registry import register


class TopicClusterTool(Tool):
    """Cluster a list of titles or short texts by common keywords (simple word overlap)."""

    name = "topic_cluster"
    description = "Find common topics across a list of text snippets. Returns top shared words."
    input_schema = {
        "type": "object",
        "properties": {
            "texts": {"type": "array", "description": "List of strings (e.g. paper titles or abstracts)"},
            "top_n": {"type": "integer", "description": "Number of top words to return (default 10)"},
        },
        "required": ["texts"],
    }

    def run(self, **kwargs) -> str:
        texts = kwargs.get("texts")
        top_n = kwargs.get("top_n", 10)
        if not isinstance(texts, list):
            return "Error: texts must be an array of strings"
        if not isinstance(top_n, int) or top_n < 1:
            top_n = 10
        stop = {"the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "with", "by", "is", "are", "be", "as", "at"}
        word_counts = Counter()
        for t in texts:
            if not isinstance(t, str):
                continue
            words = re.findall(r"\b[a-zA-Z]{3,}\b", t.lower())
            for w in words:
                if w not in stop:
                    word_counts[w] += 1
        common = word_counts.most_common(top_n)
        if not common:
            return "No significant keywords found."
        return "Top shared terms:\n" + "\n".join(f"{w}: {c}" for w, c in common)


register(TopicClusterTool())
