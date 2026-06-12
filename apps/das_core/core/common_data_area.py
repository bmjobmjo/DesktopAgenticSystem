"""Common Data Area (CDA) singleton for shared runtime state."""

from __future__ import annotations

from typing import Any, Dict


class CommonDataArea:
    _instance: "CommonDataArea | None" = None
    _initialized: bool = False

    def __new__(cls) -> "CommonDataArea":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self.__class__._initialized:
            return
        self.settings: Dict[str, Any] = {}
        self.memory: Dict[str, Any] = {}
        self.runtime_objects: Dict[str, Any] = {}
        self.session: Dict[str, Any] = {}
        self.__class__._initialized = True

    @classmethod
    def reset(cls) -> None:
        """Reset CDA state for tests."""
        if cls._instance is None:
            return
        cls._instance.settings.clear()
        cls._instance.memory.clear()
        cls._instance.runtime_objects.clear()
        cls._instance.session.clear()

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.settings[key] = value

    def get_memory(self, key: str, default: Any = None) -> Any:
        return self.memory.get(key, default)

    def set_memory(self, key: str, value: Any) -> None:
        self.memory[key] = value

    def set_runtime(self, name: str, obj: Any) -> None:
        self.runtime_objects[name] = obj

    def get_runtime(self, name: str, default: Any = None) -> Any:
        return self.runtime_objects.get(name, default)
