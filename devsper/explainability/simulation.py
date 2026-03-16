"""Simulation mode: dry-run planning and scheduling without LLM or tool execution."""

from dataclasses import dataclass, field


@dataclass
class SimulationReport:
    task_list: list[str] = field(default_factory=list)
    estimated_cost: str = "N/A"
    estimated_duration: str = "N/A"
    tool_usage_plan: list[str] = field(default_factory=list)
    model_tier_breakdown: dict = field(default_factory=dict)


class SimulationMode:
    """Dry-run: run planner and scheduler, build DecisionRecords, no LLM or tools."""

    async def simulate(self, root_task: str) -> SimulationReport:
        """Run planning and scheduling only; return SimulationReport."""
        from devsper.swarm.planner import Planner
        from devsper.swarm.scheduler import Scheduler
        from devsper.types.task import Task, TaskStatus
        from devsper.explainability.decision_tree import DecisionTreeBuilder, DecisionRecord
        from devsper.explainability.rationale import RationaleGenerator
        planner = Planner(model_name="mock", event_log=None)
        tasks = planner.plan(root_task)
        if not tasks:
            tasks = [Task(id="1", description=root_task, status=TaskStatus.PENDING)]
        scheduler = Scheduler()
        for t in tasks:
            scheduler.add_task(t)
        task_list = [t.description or t.id for t in scheduler.get_all_tasks()]
        records: list[DecisionRecord] = []
        gen = RationaleGenerator()
        for t in scheduler.get_all_tasks():
            rec = DecisionRecord(
                task_id=t.id,
                task_description=t.description or t.id,
                strategy_selected="default",
                strategy_reason="simulation",
                tools_selected=[],
                model_tier="default",
                model_selected="mock",
                model_reason="simulation",
                confidence=0.5,
                rationale="",
            )
            rec.rationale = gen.template_rationale(rec)
            records.append(rec)
        return SimulationReport(
            task_list=task_list,
            estimated_cost="N/A",
            estimated_duration="N/A",
            tool_usage_plan=[],
            model_tier_breakdown={"default": len(task_list)},
        )
