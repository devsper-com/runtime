import json

from textual.widgets import Static


class MissionView(Static):
    """Mission panel: goal, DAG, iteration progress."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._goal = ""
        self._dag = {}
        self._iteration = {}

    def set_mission(
        self,
        goal: str = "",
        dag: dict | None = None,
        iteration: dict | None = None,
    ) -> None:
        self._goal = goal or ""
        self._dag = dag or {}
        self._iteration = iteration or {}
        self._render()

    def _render(self) -> None:
        dag_tasks = self._dag.get("tasks", [])
        dag_summary = []
        for t in dag_tasks[:8]:
            deps = ",".join(t.get("dependencies", [])) or "-"
            dag_summary.append(f"- {t.get('title', '?')} [{t.get('agent', '?')}] deps={deps}")
        dag_text = "\n".join(dag_summary) if dag_summary else "(no DAG)"
        iter_text = json.dumps(self._iteration or {}, indent=2) if self._iteration else "(no iterations yet)"
        self.update(
            "Goal:\n"
            f"{(self._goal or '(none)')[:280]}\n\n"
            "DAG:\n"
            f"{dag_text}\n\n"
            "Iteration:\n"
            f"{iter_text}"
        )

    def on_mount(self) -> None:
        self._render()
