from unittest.mock import patch

from devsper.missions import MissionPlanner, MissionRunner, MissionType


def test_mission_planner_research_dag_shape():
    planner = MissionPlanner()
    dag = planner.build_dag("Write a paper on swarm systems.", MissionType.RESEARCH)
    assert dag.mission_type == MissionType.RESEARCH
    assert len(dag.tasks) == 4
    assert dag.tasks[1].dependencies == [dag.tasks[0].id]
    assert dag.tasks[-1].agent == "editor_agent"


def test_mission_runner_checkpoint_written(tmp_path):
    runner = MissionRunner(checkpoints_dir=str(tmp_path))
    with patch("devsper.missions.base_agent.generate", return_value="x" * 6000):
        result = runner.run("Build a coding project", MissionType.CODING, quality_threshold=0.7)
    assert result.quality_score >= 0.7
    assert (tmp_path / f"{result.mission_id}.json").is_file()
