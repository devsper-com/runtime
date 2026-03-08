"""
Swarm visualization: produce a simple ASCII DAG of the scheduler graph.

Input: scheduler (or its graph). Output: ASCII DAG visualization.
"""

from hivemind.swarm.scheduler import Scheduler


def visualize_scheduler_dag(scheduler: Scheduler) -> str:
    """
    Create a simple ASCII DAG visualization of the scheduler's task graph.

    Example:
        task_1
          |
        task_2
          |
        task_3
         / \\
        task_4 task_5
    """
    graph = scheduler._graph
    if graph.number_of_nodes() == 0:
        return "(empty graph)"

    try:
        import networkx as nx
        order = list(nx.topological_sort(graph))
    except Exception:
        order = list(graph.nodes())

    roots = [n for n in order if graph.in_degree(n) == 0]
    if not roots:
        roots = [order[0]]

    lines = []

    def visit(node: str, print_name: bool) -> None:
        if print_name:
            lines.append(node)
        succs = list(graph.successors(node))
        if not succs:
            return
        if len(succs) == 1:
            lines.append("  |")
            lines.append(succs[0])
            visit(succs[0], False)
        else:
            lines.append("  " + " / \\")
            lines.append("  " + " ".join(succs))
            for c in succs:
                visit(c, False)

    for r in roots:
        visit(r, True)

    return "\n".join(lines)
