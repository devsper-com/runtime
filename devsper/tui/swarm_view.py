"""
Swarm graph panel: ASCII DAG from scheduler.

Uses runtime.visualize.visualize_scheduler_dag when scheduler is set.
"""

from textual.widgets import Static


class SwarmView(Static):
    """Displays DAG visualization of the task graph."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._dag_text = "(no DAG)\n\nRun swarm to see graph."

    def set_scheduler(self, scheduler: object | None) -> None:
        """Update DAG from scheduler. Pass None to clear."""
        if scheduler is None:
            self._dag_text = "(no DAG)\n\nRun swarm to see graph."
            self.update(self._dag_text)
            return
        try:
            from devsper.runtime.visualize import visualize_scheduler_dag

            self._dag_text = visualize_scheduler_dag(scheduler)
        except Exception as e:
            self._dag_text = f"(error: {e})"
        self.update(self._dag_text)

    def set_dag_text(self, text: str) -> None:
        """Set DAG content directly (e.g. for demo)."""
        self._dag_text = text
        self.update(text)

    def on_mount(self) -> None:
        self.update(self._dag_text)
