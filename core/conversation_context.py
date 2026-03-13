"""Per-conversation context overlay.

This keeps mutable chat state local to one conversation while still allowing
shared application settings/runtime services to be resolved from the app CDA.
"""

from __future__ import annotations

from typing import Any, Dict

from core.common_data_area import CommonDataArea


class ConversationContext:
    """Overlay local memory/runtime on top of the shared application CDA."""

    def __init__(self, app_cda: CommonDataArea, conversation_id: str) -> None:
        self._app_cda = app_cda
        self.conversation_id = str(conversation_id or "").strip() or "default"
        self.settings: Dict[str, Any] = {}
        self.memory: Dict[str, Any] = {}
        self.runtime_objects: Dict[str, Any] = {}
        self.session: Dict[str, Any] = {}

    def get_setting(self, key: str, default: Any = None) -> Any:
        if key in self.settings:
            return self.settings[key]
        return self._app_cda.get_setting(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value

    def get_memory(self, key: str, default: Any = None) -> Any:
        return self.memory.get(key, default)

    def set_memory(self, key: str, value: Any) -> None:
        self.memory[key] = value

    def get_runtime(self, name: str, default: Any = None) -> Any:
        if name in self.runtime_objects:
            return self.runtime_objects[name]
        return self._app_cda.get_runtime(name, default)

    def set_runtime(self, name: str, obj: Any) -> None:
        self.runtime_objects[name] = obj

    def clear_runtime(self, name: str) -> None:
        self.runtime_objects.pop(name, None)
