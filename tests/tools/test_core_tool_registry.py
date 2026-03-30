from devsper.core.tools.registry import ToolRegistry


class _DummyTool:
    name = "dummy.tool"
    description = "dummy"


def test_registry_register_and_get():
    reg = ToolRegistry()
    tool = _DummyTool()
    reg.register(tool)
    assert reg.get("dummy.tool") is tool
    assert reg.get_with_suffix_fallback("tool") is tool


def test_registry_suffix_fallback_requires_unique_match():
    reg = ToolRegistry()
    a = _DummyTool()
    b = _DummyTool()
    b.name = "other.tool"
    reg.register(a)
    reg.register(b)
    assert reg.get_with_suffix_fallback("tool") is None

