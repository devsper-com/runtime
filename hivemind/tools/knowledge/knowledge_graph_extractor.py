"""Extract simple subject-relation-object triples from text using heuristic patterns."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown

RELATION_PATTERN = re.compile(
    r"(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:is|are|was|were|has|have|uses|used|includes|contain)\s+([^.!?]+?)(?:\.|$)",
    re.I,
)


class KnowledgeGraphExtractorTool(Tool):
    """
    Extract subject-relation-object style triples from document text (heuristic, no NER).
    """

    name = "knowledge_graph_extractor"
    description = "Extract subject-relation-object triples from a document for knowledge graph building."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Path to the document"},
            "max_triples": {"type": "integer", "description": "Max triples to return (default 50)"},
        },
        "required": ["file_path"],
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs.get("file_path")
        max_triples = kwargs.get("max_triples", 50)
        if not file_path or not isinstance(file_path, str):
            return "Error: file_path must be a non-empty string"
        if not isinstance(max_triples, int) or max_triples < 1:
            max_triples = 50
        content, err = run_docproc_to_markdown(file_path)
        if err:
            return err
        text = content or ""
        triples = []
        for m in RELATION_PATTERN.finditer(text):
            subj = m.group(1).strip()
            obj = m.group(2).strip()[:80]
            if len(subj) > 2 and len(obj) > 2:
                triples.append({"subject": subj, "object": obj})
                if len(triples) >= max_triples:
                    break
        if not triples:
            return "No triples extracted (try a document with 'X is Y' / 'X has Y' style sentences)."
        import json

        return json.dumps({"triples": triples}, indent=2)


register(KnowledgeGraphExtractorTool())
