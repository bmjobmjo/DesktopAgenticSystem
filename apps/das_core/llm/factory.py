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


def get_llm_trace_metadata(cda: CommonDataArea) -> dict[str, str]:
    """Return the provider/model configuration used for an LLM trace event."""
    provider = str(cda.get_setting('llm_provider', 'gemini') or 'gemini').strip().lower()
    model_setting_by_provider = {
        'gemini': ('gemini_model', 'gemini-1.5-flash'),
        'groq': ('groq_model', 'llama-3.3-70b-versatile'),
        'local': ('local_llm_model', 'qwen2.5-14b-instruct-1m'),
        'openrouter': ('openrouter_model', 'stepfun/step-3.5-flash'),
    }
    setting_name, default_model = model_setting_by_provider.get(provider, ('', 'mock'))
    model = str(cda.get_setting(setting_name, default_model) if setting_name else default_model).strip() or default_model
    return {'llm_provider': provider if provider in model_setting_by_provider else 'mock', 'llm_model': model}

