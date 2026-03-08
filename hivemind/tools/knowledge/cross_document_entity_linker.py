"""Link entities (capitalized phrases) across documents by matching exact strings."""

import re
from pathlib import Path

from hivemind.tools.base import Tool
from hivemind.tools.registry import register
from hivemind.tools.documents._docproc import run_docproc_to_markdown


class CrossDocumentEntityLinkerTool(Tool):
    """
    Extract capitalized multi-word phrases as candidate entities and link them across documents.
    """

    name = "cross_document_entity_linker"
    description = "Link entities (capitalized phrases) across multiple documents."
    input_schema = {
        "type": "object",
        "properties": {
            "file_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of paths to documents",
            },
            "min_phrase_length": {"type": "integer", "description": "Min words in phrase (default 2)"},
        },
        "required": ["file_paths"],
    }

    def _extract_entities(self, text: str, min_words: int) -> set[str]:
        pat = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
        phrases = set()
        for m in pat.finditer(text):
            phrase = m.group(1).strip()
            if len(phrase.split()) >= min_words:
                phrases.add(phrase)
        return phrases

    def run(self, **kwargs) -> str:
        file_paths = kwargs.get("file_paths")
        min_words = kwargs.get("min_phrase_length", 2)
        if not file_paths or not isinstance(file_paths, list):
            return "Error: file_paths must be a non-empty list of strings"
        if not isinstance(min_words, int) or min_words < 1:
            min_words = 2
        doc_entities = {}
        all_entities = set()
        for path in file_paths:
            if not isinstance(path, str) or not path.strip():
                continue
            p = Path(path.strip()).resolve()
            if not p.exists() or not p.is_file():
                continue
            content, err = run_docproc_to_markdown(str(p))
            if err:
                continue
            entities = self._extract_entities(content or "", min_words)
            doc_entities[p.name] = list(entities)
            all_entities |= entities
        cross = {e: [name for name, ents in doc_entities.items() if e in ents] for e in all_entities}
        cross = {k: v for k, v in cross.items() if len(v) > 1}
        import json

        return json.dumps(
            {"documents": list(doc_entities.keys()), "cross_document_entities": cross, "per_doc": doc_entities},
            indent=2,
        )


register(CrossDocumentEntityLinkerTool())
