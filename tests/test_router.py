"""Test provider router: model name → provider, generate(model, prompt) via utils.models."""
from hivemind.providers.router import ProviderRouter, _model_to_vendor
from hivemind.utils.models import generate


def test_model_to_vendor_routing():
    """Router maps model names to the correct vendor."""
    assert _model_to_vendor("gpt-4o") == "openai"
    assert _model_to_vendor("o1") == "openai"
    assert _model_to_vendor("claude-sonnet-4") == "anthropic"
    assert _model_to_vendor("gemini-2.5-flash") == "gemini"
    assert _model_to_vendor("mock") == "mock"
    assert _model_to_vendor("default") == "mock"
    assert _model_to_vendor("") == "mock"
    assert _model_to_vendor("unknown") == "mock"


def test_generate_mock_uses_mock_provider():
    """generate('mock', prompt) goes through router and returns MockProvider output (no API key)."""
    out = generate("mock", "Hello world")
    assert out == "Completed: Hello world"
    long_prompt = "x" * 250
    out2 = generate("mock", long_prompt)
    assert out2.startswith("Completed:")
    assert "..." in out2


def test_router_caches_mock_provider():
    """get_provider returns the same MockProvider instance for mock/default."""
    router = ProviderRouter()
    mock1 = router.get_provider("mock")
    mock2 = router.get_provider("default")
    assert mock1 is mock2
