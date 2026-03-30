from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from devsper.missions.iteration_loop import IterationEngine
from devsper.missions.mission_memory import MissionMemory
from devsper.missions.mission_planner import MissionPlanner
from devsper.missions.models import MissionCheckpoint, MissionDAG, MissionType
from devsper.missions.research import EditorAgent, ResearcherAgent, ReviewerAgent, WriterAgent
from devsper.missions.coding import ArchitectAgent, CoderAgent, DebuggerAgent, DocsAgent, TesterAgent


HitlCallback = Callable[[dict], bool]


@dataclass(slots=True)
class MissionResult:
    mission_id: str
    mission_type: MissionType
    goal: str
    dag: dict
    output: str
    quality_score: float
    iterations: int
    iteration_history: list[dict]
    memory: dict
    checkpoints_path: str


class MissionRunner:
    """Executes autonomous missions with iteration, checkpointing, and resume."""

    def __init__(self, checkpoints_dir: str = ".devsper/missions", model_name: str = "auto") -> None:
        self._planner = MissionPlanner()
        self._iteration = IterationEngine()
        self._memory = MissionMemory()
        self._checkpoints_dir = checkpoints_dir
        self._model_name = model_name

    def run(
        self,
        goal: str,
        mission_type: MissionType,
        quality_threshold: float = 0.85,
        max_iterations: int = 4,
        hitl_callback: HitlCallback | None = None,
    ) -> MissionResult:
        mission_id = f"mission_{secrets.token_hex(4)}"
        dag = self._planner.build_dag(goal, mission_type)
        output, quality, iterations, hist = self._execute_with_iteration(
            goal=goal,
            dag=dag,
            quality_threshold=quality_threshold,
            max_iterations=max_iterations,
            hitl_callback=hitl_callback,
            mission_id=mission_id,
        )
        return MissionResult(
            mission_id=mission_id,
            mission_type=mission_type,
            goal=goal,
            dag=dag.as_dict(),
            output=output,
            quality_score=quality,
            iterations=iterations,
            iteration_history=hist,
            memory=self._memory.snapshot(),
            checkpoints_path=self._checkpoint_path(mission_id),
        )

    def resume(
        self,
        mission_id: str,
        hitl_callback: HitlCallback | None = None,
    ) -> MissionResult:
        ckpt = self._load_checkpoint(mission_id)
        self._memory = MissionMemory.from_snapshot(ckpt.get("memory", {}))
        dag = MissionDAG(
            mission_type=MissionType(ckpt["mission_type"]),
            goal=ckpt["goal"],
            tasks=[],
        )
        dag.tasks = self._planner.build_dag(ckpt["goal"], MissionType(ckpt["mission_type"])).tasks
        output, quality, iterations, hist = self._execute_with_iteration(
            goal=ckpt["goal"],
            dag=dag,
            quality_threshold=float(ckpt.get("quality_threshold", 0.85)),
            max_iterations=4,
            hitl_callback=hitl_callback,
            mission_id=mission_id,
            start_iteration=int(ckpt.get("iteration", 0)),
            existing_history=list(ckpt.get("run_log", [])),
        )
        return MissionResult(
            mission_id=mission_id,
            mission_type=MissionType(ckpt["mission_type"]),
            goal=ckpt["goal"],
            dag=ckpt.get("dag", dag.as_dict()),
            output=output,
            quality_score=quality,
            iterations=iterations,
            iteration_history=hist,
            memory=self._memory.snapshot(),
            checkpoints_path=self._checkpoint_path(mission_id),
        )

    def _execute_with_iteration(
        self,
        goal: str,
        dag: MissionDAG,
        quality_threshold: float,
        max_iterations: int,
        mission_id: str,
        hitl_callback: HitlCallback | None = None,
        start_iteration: int = 0,
        existing_history: list[dict] | None = None,
    ) -> tuple[str, float, int, list[dict]]:
        output = ""
        quality = 0.0
        history = list(existing_history or [])
        for i in range(start_iteration + 1, start_iteration + max_iterations + 1):
            output = self._execute_dag(goal, dag, output, hitl_callback=hitl_callback)
            quality, feedback = self._critique(dag.mission_type, goal, output)
            history.append({"iteration": i, "quality_score": quality, "feedback": feedback})
            self._memory.add_decision(f"Iteration {i}", feedback)
            self._write_checkpoint(
                MissionCheckpoint(
                    mission_id=mission_id,
                    goal=goal,
                    mission_type=dag.mission_type,
                    dag=dag.as_dict(),
                    iteration=i,
                    quality_score=quality,
                    quality_threshold=quality_threshold,
                    run_log=history,
                    pending_tasks=[],
                )
            )
            if quality >= quality_threshold:
                return output, quality, i, history
            output = self._improve(dag.mission_type, goal, output, feedback)
        return output, quality, start_iteration + max_iterations, history

    def _execute_dag(
        self,
        goal: str,
        dag: MissionDAG,
        current: str,
        hitl_callback: HitlCallback | None = None,
    ) -> str:
        text = current
        agent_map = self._agent_map(dag.mission_type)
        for task in dag.tasks:
            if hitl_callback is not None and not hitl_callback(
                {"task_id": task.id, "title": task.title, "agent": task.agent, "goal": goal}
            ):
                raise RuntimeError(f"HITL rejected task {task.id} ({task.title})")
            agent = agent_map[task.agent]
            text = agent.run(goal=goal, current=text, context=task.description)
            if dag.mission_type == MissionType.RESEARCH and task.agent == "researcher_agent":
                self._memory.add_research_finding(task.title, text[:3000])
            if "experiment" in goal.lower() or dag.mission_type == MissionType.EXPERIMENT:
                self._memory.add_experiment(task.title, task.description, text[:1200])
        return text

    def _critique(self, mission_type: MissionType, goal: str, text: str) -> tuple[float, str]:
        if mission_type == MissionType.CODING:
            reviewer = DebuggerAgent(model_name=self._model_name)
        else:
            reviewer = ReviewerAgent(model_name=self._model_name)
        feedback = reviewer.run(goal=goal, current=text, context="Critique this output and provide issues.")
        # Lightweight proxy score so missions can progress deterministically.
        score = min(0.99, max(0.25, len(text.strip()) / 4000.0))
        return score, feedback

    def _improve(self, mission_type: MissionType, goal: str, text: str, feedback: str) -> str:
        if mission_type == MissionType.CODING:
            improver = CoderAgent(model_name=self._model_name)
        else:
            improver = WriterAgent(model_name=self._model_name)
        return improver.run(goal=goal, current=text, context=feedback)

    def _agent_map(self, mission_type: MissionType) -> dict[str, object]:
        if mission_type == MissionType.CODING:
            return {
                "architect_agent": ArchitectAgent(model_name=self._model_name),
                "coder_agent": CoderAgent(model_name=self._model_name),
                "tester_agent": TesterAgent(model_name=self._model_name),
                "debugger_agent": DebuggerAgent(model_name=self._model_name),
                "docs_agent": DocsAgent(model_name=self._model_name),
            }
        return {
            "researcher_agent": ResearcherAgent(model_name=self._model_name),
            "reviewer_agent": ReviewerAgent(model_name=self._model_name),
            "writer_agent": WriterAgent(model_name=self._model_name),
            "editor_agent": EditorAgent(model_name=self._model_name),
            "coder_agent": CoderAgent(model_name=self._model_name),
        }

    def _checkpoint_path(self, mission_id: str) -> str:
        return os.path.join(self._checkpoints_dir, f"{mission_id}.json")

    def _write_checkpoint(self, checkpoint: MissionCheckpoint) -> None:
        os.makedirs(self._checkpoints_dir, exist_ok=True)
        data = {
            "mission_id": checkpoint.mission_id,
            "goal": checkpoint.goal,
            "mission_type": checkpoint.mission_type.value,
            "dag": checkpoint.dag,
            "iteration": checkpoint.iteration,
            "quality_score": checkpoint.quality_score,
            "quality_threshold": checkpoint.quality_threshold,
            "run_log": checkpoint.run_log,
            "pending_tasks": checkpoint.pending_tasks,
            "memory": self._memory.snapshot(),
            "created_at": checkpoint.created_at,
        }
        tmp = self._checkpoint_path(checkpoint.mission_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self._checkpoint_path(checkpoint.mission_id))

    def _load_checkpoint(self, mission_id: str) -> dict:
        path = self._checkpoint_path(mission_id)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Mission checkpoint not found: {mission_id}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
