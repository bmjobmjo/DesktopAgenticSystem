"""Base interface for LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseLLMClient(ABC):
    @abstractmethod
    def generate(
        self, 
        prompt: str, 
        agent_name: str = "Assistant", 
        user_prompt: str = "",
        attachments: List[Dict[str, Any]] | None = None,
    ) -> str:  # pragma: no cover - interface only
        raise NotImplementedError
