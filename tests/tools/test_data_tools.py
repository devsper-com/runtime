"""Tests for data tools."""

import tempfile
from pathlib import Path

import pytest

from devsper.tools.data.csv_summary import CsvSummaryTool
from devsper.tools.data.json_query import JsonQueryTool
from devsper.tools.data.json_pretty_print import JsonPrettyPrintTool
from devsper.tools.data.column_type_detection import ColumnTypeDetectionTool
from devsper.tools.data.missing_value_report import MissingValueReportTool
from devsper.tools.data.dataset_sampling import DatasetSamplingTool
from devsper.tools.data.dataset_schema import DatasetSchemaTool


def test_csv_summary():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("a,b,c\n1,2,3\n4,5,6\n")
        path = f.name
    try:
        out = CsvSummaryTool().run(path=path, sample_rows=2)
        assert "a" in out and "b" in out and "Row count" in out
    finally:
        Path(path).unlink(missing_ok=True)


def test_json_query():
    out = JsonQueryTool().run(json_str='{"a": {"b": [1, 2]}}', path="a.b.0")
    assert out == "1"


def test_json_pretty_print():
    out = JsonPrettyPrintTool().run(json_str='{"a":1}')
    assert "a" in out and "1" in out


def test_column_type_detection():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("x,y\n1,2.5\n3,4.0\n")
        path = f.name
    try:
        out = ColumnTypeDetectionTool().run(path=path)
        assert "x" in out and "y" in out
    finally:
        Path(path).unlink(missing_ok=True)


def test_missing_value_report():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("a,b\n1,\n3,4\n")
        path = f.name
    try:
        out = MissingValueReportTool().run(path=path)
        assert "missing" in out.lower() or "b" in out
    finally:
        Path(path).unlink(missing_ok=True)


def test_dataset_sampling():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("x\n1\n2\n3\n4\n5\n")
        path = f.name
    try:
        out = DatasetSamplingTool().run(path=path, n=2)
        assert "x" in out and "\n" in out
    finally:
        Path(path).unlink(missing_ok=True)


def test_dataset_schema():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("a,b\n1,2\n")
        path = f.name
    try:
        out = DatasetSchemaTool().run(path=path)
        assert "Columns" in out and "a" in out
    finally:
        Path(path).unlink(missing_ok=True)
