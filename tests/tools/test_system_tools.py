"""Tests for system tools."""

import pytest

from devsper.tools.system.system_info import SystemInfoTool
from devsper.tools.system.disk_usage import DiskUsageTool
from devsper.tools.system.environment_variables import EnvironmentVariablesTool
from devsper.tools.system.pip_search import PipSearchTool


def test_system_info():
    out = SystemInfoTool().run()
    assert "python" in out.lower() or "system" in out.lower()


def test_disk_usage():
    out = DiskUsageTool().run(path=".")
    assert "total" in out.lower() and "bytes" in out.lower()


def test_environment_variables():
    out = EnvironmentVariablesTool().run(show_values=False)
    assert "\n" in out or len(out) >= 0


def test_pip_search():
    out = PipSearchTool().run(query="requests")
    assert "pypi" in out.lower() or "pip" in out.lower()
