"""Tests for experiment tools."""

import json
import pytest

from hivemind.tools.experiments.parameter_sweep_runner import ParameterSweepRunnerTool
from hivemind.tools.experiments.grid_search_runner import GridSearchRunnerTool
from hivemind.tools.experiments.experiment_tracker import ExperimentTrackerTool
from hivemind.tools.experiments.result_comparator import ResultComparatorTool
from hivemind.tools.experiments.model_benchmark_runner import ModelBenchmarkRunnerTool
from hivemind.tools.experiments.simulation_runner import SimulationRunnerTool
from hivemind.tools.experiments.monte_carlo_experiment import MonteCarloExperimentTool
from hivemind.tools.experiments.statistical_significance_test import StatisticalSignificanceTestTool
from hivemind.tools.experiments.bootstrap_estimator import BootstrapEstimatorTool
from hivemind.tools.experiments.experiment_report_generator import ExperimentReportGeneratorTool
from hivemind.tools.experiments.swarm_map_reduce import SwarmMapReduceTool


def test_parameter_sweep_runner():
    out = ParameterSweepRunnerTool().run(params={"lr": [0.01, 0.1], "epochs": [5]})
    data = json.loads(out)
    assert "combinations" in data
    assert len(data["combinations"]) == 2


def test_parameter_sweep_runner_invalid():
    out = ParameterSweepRunnerTool().run(params=None)
    assert "Error" in out


def test_grid_search_runner():
    out = GridSearchRunnerTool().run(param_grid={"a": [1, 2], "b": [3]})
    data = json.loads(out)
    assert data["grid_size"] == 2
    assert len(data["combinations"]) == 2


def test_experiment_tracker():
    out = ExperimentTrackerTool().run(run_id="run1", params={"lr": 0.01}, metrics={"loss": 0.5})
    data = json.loads(out)
    assert "logged" in data
    assert data["logged"]["run_id"] == "run1"


def test_experiment_tracker_no_run_id():
    out = ExperimentTrackerTool().run()
    assert "Error" in out


def test_result_comparator():
    out = ResultComparatorTool().run(
        results=[{"run_id": "a", "metrics": {"acc": 0.9}}, {"run_id": "b", "metrics": {"acc": 0.8}}],
        metric="acc",
    )
    data = json.loads(out)
    assert "best_run_id" in data
    assert data["best_value"] == 0.9


def test_model_benchmark_runner():
    out = ModelBenchmarkRunnerTool().run(iterations=2, delay_seconds=0)
    data = json.loads(out)
    assert data["iterations"] == 2
    assert "mean_seconds" in data


def test_simulation_runner():
    out = SimulationRunnerTool().run(initial_value=1.0, steps=5, growth_rate=1.1)
    assert "Final value" in out
    assert "1.1" in out or "1.46" in out or "Trajectory" in out


def test_monte_carlo_experiment():
    out = MonteCarloExperimentTool().run(n_samples=10, low=0, high=1)
    assert "mean" in out.lower()
    assert "10" in out


def test_statistical_significance_test():
    out = StatisticalSignificanceTestTool().run(sample_a=[1.0, 2.0, 3.0], sample_b=[1.1, 2.1, 2.9])
    assert "t-statistic" in out or "Mean" in out


def test_bootstrap_estimator():
    out = BootstrapEstimatorTool().run(values=[1.0, 2.0, 3.0, 4.0, 5.0], n_bootstrap=20)
    assert "CI" in out or "estimate" in out.lower()


def test_experiment_report_generator():
    out = ExperimentReportGeneratorTool().run(runs=[{"run_id": "r1", "metrics": {"acc": 0.9}}])
    assert "r1" in out
    assert "Report" in out or "runs" in out


def test_swarm_map_reduce():
    out = SwarmMapReduceTool().run(items=["a", "b", "c", "d", "e"], batch_size=2)
    data = json.loads(out)
    assert data["total_items"] == 5
    assert len(data["batches"]) == 3
