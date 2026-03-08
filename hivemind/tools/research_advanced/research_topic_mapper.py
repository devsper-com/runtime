"""Map research topics across documents: term frequency and co-occurrence style groups."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

STOP = frozenset("a an the and or but in on at to for of with by from as is was are were been be have has had do does did will would could should may might must can this that it its".split())


class ResearchTopicMapperTool(Tool):
    """
    Map topics across documents: high-frequency terms per doc and shared terms.
    """

    name = "research_topic_mapper"
    description = "Map research topics across documents (term frequency and shared terms)."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to papers",
            },
            "top_per_doc": {"type": "integer", "description": "Top N terms per doc (default 10)"},
        },
        "required": ["file_paths"],
    }

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        top_per_doc = kwargs.get("top_per_doc", 10)
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list"
        if not isinstance(top_per_doc, int) or top_per_doc < 1:
            top_per_doc = 10
        doc_topics = {}
        all_terms = set()
        for path in file_paths:
            if not isinstance(path, str) or not path.strip():
                continue
            p = Path(path.strip()).resolve()
            if not p.exists() or not p.is_file():
                continue
            content, err = run_docproc_to_markdown(str(p))
            if err:
                continue
            words = [w for w in re.findall(r"[a-z]+", (content or "").lower()) if len(w) >= 4 and w not in STOP]
            from collections import Counter

            top = [w for w, _ in Counter(words).most_common(top_per_doc)]
            doc_topics[p.name] = top
            all_terms.update(top)
        shared = []
        for t in all_terms:
            count = sum(1 for tops in doc_topics.values() if t in tops)
            if count > 1:
                shared.append(t)
        lines = ["Topic map", "=" * 40]
        for name, topics in doc_topics.items():
            lines.append(f"{name}: " + ", ".join(topics))
        lines.append("\nShared topics: " + ", ".join(shared[:20]))
        return "\n".join(lines)


register(ResearchTopicMapperTool())
