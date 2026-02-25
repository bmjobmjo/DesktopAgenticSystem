"""Base interface for LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(
        self, 
        prompt: str, 
        agent_name: str = "Assistant", 
        user_prompt: str = ""
    ) -> str:  # pragma: no cover - interface only
        raise NotImplementedError
