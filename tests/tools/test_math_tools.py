"""Tests for math tools."""

import pytest

from devsper.tools.math.calculate_expression import CalculateExpressionTool
from devsper.tools.math.mean_std import MeanStdTool
from devsper.tools.math.correlation import CorrelationTool
from devsper.tools.math.histogram import HistogramTool
from devsper.tools.math.random_sample import RandomSampleTool
from devsper.tools.math.distribution_summary import DistributionSummaryTool


def test_calculate_expression():
    out = CalculateExpressionTool().run(expression="2 + 3 * 4")
    assert out == "14"


def test_mean_std():
    out = MeanStdTool().run(values=[1.0, 2.0, 3.0])
    assert "2" in out and "mean" in out.lower()


def test_correlation():
    out = CorrelationTool().run(x=[1, 2, 3], y=[2, 4, 6])
    assert "1" in out or "r =" in out


def test_histogram():
    out = HistogramTool().run(values=[1, 2, 3, 4, 5] * 4, bins=5)
    assert "[" in out and ")" in out


def test_random_sample():
    out = RandomSampleTool().run(values=[1, 2, 3, 4, 5], k=2)
    assert "[" in out and "]" in out


def test_distribution_summary():
    out = DistributionSummaryTool().run(values=[1.0, 2.0, 3.0, 4.0, 5.0])
    assert "min" in out.lower() and "max" in out.lower() and "mean" in out.lower()
