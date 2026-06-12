"""Factory for creating LLM clients based on configuration."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.common_data_area import CommonDataArea
    from llm.base_client import BaseLLMClient

def get_llm_client(cda: CommonDataArea) -> BaseLLMClient:
    """Creates an LLM client instance based on current CDA settings."""
    from llm.gemini_client import GeminiClient
    from llm.groq_client import GroqClient
    from llm.local_client import LocalLLMClient
    from llm.mock_client import MockLLMClient
    from llm.openrouter_client import OpenRouterClient

    provider = cda.get_setting('llm_provider', 'gemini')
    
    if provider == 'gemini':
        return GeminiClient(cda)
    elif provider == 'groq':
        return GroqClient(cda)
    elif provider == 'local':
        return LocalLLMClient(cda)
    elif provider == 'openrouter':
        return OpenRouterClient(cda)
    else:
        return MockLLMClient()

