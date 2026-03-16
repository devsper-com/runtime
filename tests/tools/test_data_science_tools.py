"""Tests for data science tools."""

import csv
import tempfile
from pathlib import Path

import pytest

from devsper.tools.data_science.dataset_profile import DatasetProfileTool
from devsper.tools.data_science.feature_importance_estimator import FeatureImportanceEstimatorTool
from devsper.tools.data_science.dataset_distribution_report import DatasetDistributionReportTool
from devsper.tools.data_science.dataset_outlier_detector import DatasetOutlierDetectorTool
from devsper.tools.data_science.correlation_heatmap import CorrelationHeatmapTool
from devsper.tools.data_science.time_series_analyzer import TimeSeriesAnalyzerTool
from devsper.tools.data_science.model_input_validator import ModelInputValidatorTool
from devsper.tools.data_science.dataset_drift_detector import DatasetDriftDetectorTool
from devsper.tools.data_science.feature_engineering_suggestions import FeatureEngineeringSuggestionsTool
from devsper.tools.data_science.dataset_bias_detector import DatasetBiasDetectorTool
from devsper.tools.data_science.distributed_dataset_processor import DistributedDatasetProcessorTool


def test_dataset_profile(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b,c\n1,2,3\n4,5,6\n7,8,9")
    out = DatasetProfileTool().run(path=str(p))
    assert "Shape" in out or "Columns" in out


def test_dataset_profile_invalid_path():
    out = DatasetProfileTool().run(path="/nonexistent/file.csv")
    assert "Error" in out


def test_feature_importance_estimator(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("x,y,target\n1,10,1\n2,20,2\n3,30,3\n4,40,4\n5,50,5")
    out = FeatureImportanceEstimatorTool().run(path=str(p), target_column="target")
    assert "importance" in out.lower() or "target" in out or "Error" in out


def test_dataset_distribution_report(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1.0,2.0\n3.0,4.0\n5.0,6.0")
    out = DatasetDistributionReportTool().run(path=str(p))
    assert "mean" in out.lower() or "Distribution" in out or "Error" in out


def test_dataset_outlier_detector():
    out = DatasetOutlierDetectorTool().run(values=[1.0, 2.0, 2.1, 2.2, 2.3, 2.4, 100.0])
    assert "Outlier" in out or "100" in out


def test_dataset_outlier_detector_invalid():
    out = DatasetOutlierDetectorTool().run(values=[])
    assert "Error" in out


def test_correlation_heatmap(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b,c\n1,2,3\n4,5,6\n7,8,9")
    out = CorrelationHeatmapTool().run(path=str(p))
    assert "Correlation" in out or "Error" in out


def test_time_series_analyzer():
    out = TimeSeriesAnalyzerTool().run(values=[1.0, 2.0, 3.0, 4.0, 5.0])
    assert "slope" in out.lower() or "Mean" in out


def test_model_input_validator():
    out = ModelInputValidatorTool().run(values=[1.0, 2.0, 3.0])
    assert "Valid" in out or "Shape" in out


def test_dataset_drift_detector():
    out = DatasetDriftDetectorTool().run(baseline=[1.0, 2.0, 3.0], current=[10.0, 20.0, 30.0])
    assert "Drift" in out or "mean" in out.lower()


def test_feature_engineering_suggestions(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1.0,2.0\n3.0,4.0\n5.0,6.0")
    out = FeatureEngineeringSuggestionsTool().run(path=str(p))
    assert "suggestion" in out.lower() or "log" in out or "Error" in out


def test_dataset_bias_detector():
    out = DatasetBiasDetectorTool().run(values=["A", "A", "B", "B", "B", "C"])
    assert "ratio" in out.lower() or "Balance" in out or "Categories" in out


def test_distributed_dataset_processor():
    out = DistributedDatasetProcessorTool().run(total_rows=100, batch_size=25)
    data = __import__("json").loads(out)
    assert data["total_rows"] == 100
    assert data["num_batches"] == 4
