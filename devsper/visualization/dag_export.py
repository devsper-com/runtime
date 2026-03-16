"""
Export task DAG to Mermaid or Graphviz format.

DAG is loaded from a JSON file written by the swarm run (run_id_dag.json).
"""

import json
from pathlib import Path


def _safe_id(node_id: str) -> str:
    """Mermaid/Graphviz safe node id (no spaces or special chars)."""
    return node_id.replace(" ", "_").replace("-", "_").replace(".", "_")


def load_dag(
    events_dir: str | Path, run_id: str
) -> tuple[list[dict], list[tuple[str, str]]]:
    """
    Load DAG from events_dir / {run_id}_dag.json.
    Returns (nodes: [{"id", "description"}], edges: [(from_id, to_id)]).
    """
    path = Path(events_dir) / f"{run_id}_dag.json"
    if not path.is_file():
        return [], []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes", [])
    edges = [tuple(e) for e in data.get("edges", [])]
    return nodes, edges


def export_mermaid(nodes: list[dict], edges: list[tuple[str, str]]) -> str:
    """Produce a Mermaid diagram string (flowchart)."""
    lines = ["flowchart LR"]
    for n in nodes:
        nid = _safe_id(n.get("id", ""))
        desc = (n.get("description", "") or nid).replace('"', "'")[:40]
        lines.append(f'  {nid}["{desc}"]')
    for a, b in edges:
        lines.append(f"  {_safe_id(a)} --> {_safe_id(b)}")
    return "\n".join(lines)


def export_graphviz(nodes: list[dict], edges: list[tuple[str, str]]) -> str:
    """Produce a Graphviz DOT string."""
    lines = ["digraph G {", "  rankdir=LR;"]
    for n in nodes:
        nid = _safe_id(n.get("id", ""))
        desc = (n.get("description", "") or nid).replace('"', '\\"')[:40]
        lines.append(f'  {nid} [label="{desc}"];')
    for a, b in edges:
        lines.append(f"  {_safe_id(a)} -> {_safe_id(b)};")
    lines.append("}")
    return "\n".join(lines)


def list_run_ids(events_dir: str | Path) -> list[str]:
    """List available run ids (from _dag.json files)."""
    path = Path(events_dir)
    if not path.is_dir():
        return []
    run_ids = []
    for f in path.glob("*_dag.json"):
        run_id = f.stem.replace("_dag", "")
        run_ids.append(run_id)
    return sorted(run_ids, reverse=True)
