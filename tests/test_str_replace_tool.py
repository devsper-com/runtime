"""Tests for StrReplaceFile tool."""

import json
from pathlib import Path
import pytest

from devsper.tools.workspace.str_replace import StrReplaceFile


@pytest.fixture
def tmp_file(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("def hello():\n    return 'world'\n")
    return f


def test_basic_replacement(tmp_file):
    tool = StrReplaceFile()
    result = json.loads(tool.run(file=str(tmp_file), old_str="'world'", new_str="'universe'"))
    assert result["lines_added"] == 1
    assert result["lines_removed"] == 1
    assert "diff" in result
    assert tmp_file.read_text() == "def hello():\n    return 'universe'\n"


def test_old_str_not_found(tmp_file):
    tool = StrReplaceFile()
    result = json.loads(tool.run(file=str(tmp_file), old_str="NOT_HERE", new_str="x"))
    assert result["error"] == "old_str not found in file"


def test_old_str_ambiguous(tmp_file):
    tmp_file.write_text("x = 1\nx = 1\n")
    tool = StrReplaceFile()
    result = json.loads(tool.run(file=str(tmp_file), old_str="x = 1", new_str="x = 2"))
    assert result["error"] == "old_str matches multiple locations — be more specific"


def test_file_not_found():
    tool = StrReplaceFile()
    result = json.loads(tool.run(file="/nonexistent/path/file.py", old_str="x", new_str="y"))
    assert result["error"].startswith("file not found")


def test_relative_path_resolved(tmp_path, monkeypatch):
    f = tmp_path / "foo.py"
    f.write_text("a = 1\n")
    monkeypatch.chdir(tmp_path)
    tool = StrReplaceFile()
    result = json.loads(tool.run(file="foo.py", old_str="a = 1", new_str="a = 2"))
    assert "error" not in result
    assert f.read_text() == "a = 2\n"
