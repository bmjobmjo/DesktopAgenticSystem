"""Session-scoped context adapter.

This keeps session-specific memory separate from global CDA settings/runtime.
"""

from __future__ import annotations

from typing import Any, Dict

from core.chat_session import ChatSession
from core.common_data_area import CommonDataArea


class SessionContext:
    """Adapter exposing memory-like access with session-first semantics."""

    _SESSION_MEMORY_KEYS = {
        'chat_history',
        'agent_activity',
        'agent_activity_collection',
        'AgentActivity',
        'agent_activity_step',
        'prompt_context_dict',
        'active_executor_agent',
    }

    def __init__(self, cda: CommonDataArea, session: ChatSession) -> None:
        self.cda = cda
        self.session = session

    def get_memory(self, key: str, default: Any = None) -> Any:
        if key in self._SESSION_MEMORY_KEYS:
            if key == 'chat_history':
                return self.session.chat_history
            if key == 'agent_activity':
                return self.session.agent_activity
            if key == 'agent_activity_collection' or key == 'AgentActivity':
                return self.session.agent_activity_collection
            if key == 'agent_activity_step':
                return self.session.agent_activity_step
            if key == 'prompt_context_dict':
                val = self.session.metadata.get('prompt_context_dict', {})
                return val if isinstance(val, dict) else {}
            if key == 'active_executor_agent':
                return self.session.metadata.get('active_executor_agent', default)
        return self.cda.get_memory(key, default)

    def set_memory(self, key: str, value: Any) -> None:
        if key in self._SESSION_MEMORY_KEYS:
            if key == 'chat_history':
                self.session.chat_history = str(value or '')
                return
            if key == 'agent_activity':
                self.session.agent_activity = str(value or '')
                return
            if key == 'agent_activity_collection' or key == 'AgentActivity':
                if isinstance(value, list):
                    self.session.agent_activity_collection = value
                else:
                    self.session.agent_activity_collection = []
                return
            if key == 'agent_activity_step':
                try:
                    self.session.agent_activity_step = int(value or 0)
                except Exception:
                    self.session.agent_activity_step = 0
                return
            if key == 'prompt_context_dict':
                self.session.metadata['prompt_context_dict'] = value if isinstance(value, dict) else {}
                return
            if key == 'active_executor_agent':
                self.session.metadata['active_executor_agent'] = value
                return
        self.cda.set_memory(key, value)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.cda.get_setting(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.cda.set_setting(key, value)

    def set_runtime(self, key: str, value: Any) -> None:
        self.cda.set_runtime(key, value)

    def get_runtime(self, key: str, default: Any = None) -> Any:
        return self.cda.get_runtime(key, default)
