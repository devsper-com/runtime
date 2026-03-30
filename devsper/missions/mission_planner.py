from __future__ import annotations

import secrets

from devsper.missions.models import MissionDAG, MissionTask, MissionType


class MissionPlanner:
    """
    Builds mission DAGs from a high-level goal.

    Responsibilities:
    - break goal into tasks
    - generate DAG
    - assign agents
    - define dependencies
    """

    def build_dag(self, goal: str, mission_type: MissionType) -> MissionDAG:
        if mission_type == MissionType.RESEARCH:
            return self._build_research_dag(goal)
        if mission_type == MissionType.CODING:
            return self._build_coding_dag(goal)
        if mission_type == MissionType.EXPERIMENT:
            return self._build_experiment_dag(goal)
        return self._build_general_dag(goal)

    def _build_research_dag(self, goal: str) -> MissionDAG:
        t1 = self._task("research", "Gather literature and evidence", "researcher_agent")
        t2 = self._task("critique", "Critique claims and identify weak points", "reviewer_agent", [t1.id])
        t3 = self._task("improve", "Improve argument quality and structure", "writer_agent", [t2.id])
        t4 = self._task("finalize", "Finalize polished paper draft", "editor_agent", [t3.id])
        return MissionDAG(mission_type=MissionType.RESEARCH, goal=goal, tasks=[t1, t2, t3, t4])

    def _build_coding_dag(self, goal: str) -> MissionDAG:
        t1 = self._task("design", "Design architecture and implementation plan", "architect_agent")
        t2 = self._task("code", "Implement solution and core features", "coder_agent", [t1.id])
        t3 = self._task("test", "Run validation and test suite", "tester_agent", [t2.id])
        t4 = self._task("fix", "Debug and fix failing behaviors", "debugger_agent", [t3.id])
        t5 = self._task("document", "Document design and usage", "docs_agent", [t4.id])
        return MissionDAG(mission_type=MissionType.CODING, goal=goal, tasks=[t1, t2, t3, t4, t5])

    def _build_experiment_dag(self, goal: str) -> MissionDAG:
        t1 = self._task("hypothesis", "Define experiment hypothesis and setup", "researcher_agent")
        t2 = self._task("run", "Execute experiment and collect data", "coder_agent", [t1.id])
        t3 = self._task("analyze", "Analyze outcomes and statistical quality", "reviewer_agent", [t2.id])
        t4 = self._task("report", "Write experiment report and conclusions", "writer_agent", [t3.id])
        return MissionDAG(mission_type=MissionType.EXPERIMENT, goal=goal, tasks=[t1, t2, t3, t4])

    def _build_general_dag(self, goal: str) -> MissionDAG:
        t1 = self._task("plan", "Plan mission strategy and scope", "researcher_agent")
        t2 = self._task("execute", "Execute mission tasks", "coder_agent", [t1.id])
        t3 = self._task("review", "Review quality and improve", "reviewer_agent", [t2.id])
        t4 = self._task("deliver", "Deliver final output", "editor_agent", [t3.id])
        return MissionDAG(mission_type=MissionType.GENERAL, goal=goal, tasks=[t1, t2, t3, t4])

    def _task(
        self,
        title: str,
        description: str,
        agent: str,
        dependencies: list[str] | None = None,
    ) -> MissionTask:
        return MissionTask(
            id=f"m_{secrets.token_hex(3)}",
            title=title,
            description=description,
            agent=agent,
            dependencies=dependencies or [],
        )
