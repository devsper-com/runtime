"""
Agent role activity: show which roles are active and for which tasks.
"""

from textual.widgets import Static


class AgentRoleActivityView(Static):
    """Shows agent role per task: research_agent, code_agent, analysis_agent, critic_agent."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tasks_with_roles: list[dict] = []

    def set_tasks_with_roles(self, tasks: list[dict]) -> None:
        """Update with list of {task_id, role, status}. Role can be None."""
        self._tasks_with_roles = tasks
        self._refresh_display()

    def _refresh_display(self) -> None:
        if not self._tasks_with_roles:
            self.update("(Agent roles)\n\nNo task/role data yet.")
            return
        by_role: dict[str, list[str]] = {}
        for t in self._tasks_with_roles:
            role = t.get("role") or "general"
            tid = t.get("task_id", "?")
            by_role.setdefault(role, []).append(tid)
        lines = ["(Agent role activity)", ""]
        for role in ["research_agent", "code_agent", "analysis_agent", "critic_agent", "general"]:
            if role not in by_role:
                continue
            tasks = by_role[role][:10]
            lines.append(f"  {role}: {', '.join(tasks)}")
        self.update("\n".join(lines))
