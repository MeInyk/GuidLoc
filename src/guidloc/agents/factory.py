"""LLM provider factory wired to application settings."""

from guidloc.agents.base import LLMProvider
from guidloc.agents.echo import EchoLLMProvider
from guidloc.common.config import get_settings


def get_llm_provider() -> LLMProvider:
    """Return the LLM provider configured in Settings.

    Falls back to EchoLLMProvider whenever 'openai' is not fully configured
    so the app can still boot and tests stay deterministic.
    """
    settings = get_settings()
    if settings.llm_provider.lower() == "openai" and settings.openai_api_key:
        # Imported lazily to avoid pulling the OpenAI SDK in tests.
        from guidloc.agents.openai_agent import OpenAIAgentsProvider

        return OpenAIAgentsProvider()
    return EchoLLMProvider()
