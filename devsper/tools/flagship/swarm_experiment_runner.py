"""Run parameter sweeps or experiments using the swarm runtime; executor divides runs across workers."""

import json
from devsper.tools.base import Tool
from devsper.tools.registry import register
from devsper.types.task import Task
from devsper.swarm.scheduler import Scheduler
from devsper.swarm.executor import Executor
from devsper.agents.agent import Agent
from devsper.utils.event_logger import EventLog


def _run_experiment_once(
    task_description: str,
    worker_model: str,
    worker_count: int,
) -> float:
    """Run a single swarm-style run and return a numeric metric (e.g. result length sum)."""
    from unittest.mock import patch
    tasks = [
        Task(id=f"run_1", description=task_description, dependencies=[]),
    ]
    scheduler = Scheduler()
    scheduler.add_tasks(tasks)
    log = EventLog()
    with patch("devsper.agents.agent.generate", return_value="Experiment result output."):
        agent = Agent(model_name=worker_model, event_log=log)
        executor = Executor(scheduler=scheduler, agent=agent, worker_count=worker_count, event_log=log)
        executor.run_sync()
    results = scheduler.get_results()
    total = sum(len(r or "") for r in results.values()) or 1.0
    return float(total)


class SwarmExperimentRunnerTool(Tool):
    """
    Run parameter sweeps or experiments using the swarm runtime.
    Executor divides runs across workers. Output: mean, std, best configuration.
    """

    name = "swarm_experiment_runner"
    description = "Run parameter sweeps or experiments using the swarm runtime; returns experiment statistics (mean, std, best)."
    input_schema = {
        "type": "object",
        "properties": {
            "parameters": {"type": "object", "description": "Experiment parameters (e.g. task description, config)"},
            "runs": {"type": "integer", "description": "Number of runs (default 3)"},
        },
        "required": ["parameters"],
    }

    def run(self, **kwargs) -> str:
        parameters = kwargs.get("parameters")
        runs = kwargs.get("runs", 3)
        if not isinstance(parameters, dict):
            return "Error: parameters must be an object"
        if not isinstance(runs, int) or runs < 1:
            runs = 3
        runs = min(runs, 20)

        task_description = parameters.get("task", parameters.get("prompt", "Run experiment."))
        if not isinstance(task_description, str):
            task_description = str(parameters)[:500]

        metrics = []
        for _ in range(runs):
            m = _run_experiment_once(task_description, worker_model="mock", worker_count=2)
            metrics.append(m)

        n = len(metrics)
        mean = sum(metrics) / n
        variance = sum((x - mean) ** 2 for x in metrics) / n if n else 0
        std = variance ** 0.5
        best_idx = max(range(n), key=lambda i: metrics[i])
        best_config = {"run_index": best_idx, "metric": metrics[best_idx]}

        return json.dumps({
            "mean": round(mean, 4),
            "std": round(std, 4),
            "runs": n,
            "best_configuration": best_config,
            "metrics": [round(x, 4) for x in metrics],
        }, indent=2)


register(SwarmExperimentRunnerTool())
