from __future__ import annotations
import re
import tomllib
from .ir import RawWorkflowDoc, GraphSpec, NodeSpec, EdgeSpec


def parse(text: str) -> tuple[RawWorkflowDoc, GraphSpec]:
    """
    Parse prose, TOML, or markdown into (RawWorkflowDoc, seed GraphSpec).
    Detection order: TOML if it contains key=value patterns, markdown if it
    starts with # or contains bullet lists, else treated as prose.
    """
    text = text.strip()
    if _looks_like_toml(text):
        return _parse_toml(text)
    if _looks_like_markdown(text):
        return _parse_markdown(text)
    return _parse_prose(text)


def _looks_like_toml(text: str) -> bool:
    return bool(re.search(r"^\w+\s*=", text, re.MULTILINE)) and "\n" in text


def _looks_like_markdown(text: str) -> bool:
    return text.startswith("#") or bool(re.search(r"^[-*]\s", text, re.MULTILINE))


def _parse_toml(text: str) -> tuple[RawWorkflowDoc, GraphSpec]:
    data = tomllib.loads(text)
    doc = RawWorkflowDoc(
        title=data.get("title", ""),
        description=data.get("description", ""),
        agents=data.get("agents", []),
        raw_text=text,
    )
    nodes = [
        NodeSpec(
            id=agent.get("id", f"node_{i}"),
            role=agent.get("role", ""),
            tools=agent.get("tools", []),
            model_hint=agent.get("model", "mid"),
            is_mutation_point=agent.get("mutation_point", False),
        )
        for i, agent in enumerate(doc.agents)
    ]
    if not nodes:
        nodes = [NodeSpec(id="node_0", role=doc.description or doc.title or "Execute task")]
    return doc, GraphSpec(nodes=nodes, edges=_linear_edges(nodes))


def _parse_markdown(text: str) -> tuple[RawWorkflowDoc, GraphSpec]:
    doc = RawWorkflowDoc(raw_text=text)
    title_match = re.search(r"^#+\s+(.+)$", text, re.MULTILINE)
    if title_match:
        doc.title = title_match.group(1).strip()
    steps = re.findall(r"^[-*\d.]+\s+(.+)$", text, re.MULTILINE)
    doc.steps = [s.strip() for s in steps if len(s.strip()) > 5]
    if not doc.steps:
        doc.steps = [text[:200]]
    nodes = [NodeSpec(id=f"step_{i}", role=step) for i, step in enumerate(doc.steps)]
    return doc, GraphSpec(nodes=nodes, edges=_linear_edges(nodes))


def _parse_prose(text: str) -> tuple[RawWorkflowDoc, GraphSpec]:
    doc = RawWorkflowDoc(description=text, raw_text=text)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 10]
    if not sentences:
        sentences = [text[:200]]
    step_size = max(1, len(sentences) // min(5, len(sentences)))
    steps = [
        " ".join(sentences[i : i + step_size])
        for i in range(0, len(sentences), step_size)
    ][:5]
    nodes = [NodeSpec(id=f"node_{i}", role=step) for i, step in enumerate(steps)]
    return doc, GraphSpec(nodes=nodes, edges=_linear_edges(nodes))


def _linear_edges(nodes: list[NodeSpec]) -> list[EdgeSpec]:
    return [EdgeSpec(src=nodes[i].id, dst=nodes[i + 1].id) for i in range(len(nodes) - 1)]
