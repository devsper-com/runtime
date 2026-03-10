"""
Shared configuration for examples. Loads .env (GITHUB_TOKEN, OPENAI_API_KEY, AZURE_OPENAI_*, etc.)
and provides model names. Use mock models when no API key is set so examples run without keys.
GitHub provider (gh): set GITHUB_TOKEN for github:gpt-4o. Azure/OpenAI/Anthropic/Gemini also supported.
"""

import os

from dotenv import load_dotenv

_load_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_load_path)


def get_worker_model() -> str:
    override = os.environ.get("HIVEMIND_WORKER_MODEL")
    if override:
        return override
    if os.environ.get("GITHUB_TOKEN"):
        return "github:gpt-4o"
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"):
        return "gpt-5-mini"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("AZURE_ANTHROPIC_ENDPOINT") or os.environ.get("AZURE_ANTHROPIC_API_KEY"):
        return "claude-opus-4-6-2"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-3-haiku-20240307"
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini-1.5-flash"
    return "mock"


def get_planner_model() -> str:
    override = os.environ.get("HIVEMIND_PLANNER_MODEL")
    if override:
        return override
    if os.environ.get("GITHUB_TOKEN"):
        return "github:gpt-4o"
    if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY"):
        return "gpt-4o"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    if os.environ.get("AZURE_ANTHROPIC_ENDPOINT") or os.environ.get("AZURE_ANTHROPIC_API_KEY"):
        return "claude-opus-4-6-2"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-3-haiku-20240307"
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini-1.5-flash"
    return "mock"
