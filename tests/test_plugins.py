"""Tests for plugin loading (entry_points)."""

from unittest.mock import patch

from hivemind.plugins.plugin_loader import load_plugins
from hivemind.plugins.plugin_registry import list_plugins, clear_plugins


def test_load_plugins_no_entry_points():
    """With no hivemind.plugins entry points, load_plugins returns empty or runs without error."""
    clear_plugins()
    with patch("hivemind.plugins.plugin_loader._load_entry_points", return_value=[]):
        loaded = load_plugins()
    assert loaded == []


def test_plugin_registry_clear():
    clear_plugins()
    assert len(list_plugins()) == 0
