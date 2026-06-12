"""Session domain model and registry for per-user/per-interface chat state."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


SessionKey = Tuple[str, str, str]


def _norm(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text else fallback


@dataclass
class ChatSession:
    user_id: str
    interface: str
    session_id: str = "default"

    task_queue: List[Dict[str, Any]] = field(default_factory=list)
    current_task: Optional[Dict[str, Any]] = None
    awaiting_user_input: bool = False

    chat_history: str = ""
    agent_activity: str = ""
    agent_activity_collection: List[Dict[str, Any]] = field(default_factory=list)
    agent_activity_step: int = 0
    current_chat_id: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)
    last_access_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

    def key(self) -> SessionKey:
        return (
            _norm(self.user_id, "unknown"),
            _norm(self.interface, "UI"),
            _norm(self.session_id, "default"),
        )

    def touch(self) -> None:
        self.last_access_utc = datetime.now(timezone.utc)


class SessionStore:
    """Thread-safe registry for chat sessions."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[SessionKey, ChatSession] = {}

    @staticmethod
    def _make_key(user_id: Any, interface: Any, session_id: Any = "default") -> SessionKey:
        return (
            _norm(user_id, "unknown"),
            _norm(interface, "UI"),
            _norm(session_id, "default"),
        )

    def get_or_create(self, user_id: Any, interface: Any, session_id: Any = "default") -> ChatSession:
        key = self._make_key(user_id, interface, session_id)
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                session = ChatSession(user_id=key[0], interface=key[1], session_id=key[2])
                self._sessions[key] = session
            session.touch()
            return session

    def get(self, user_id: Any, interface: Any, session_id: Any = "default") -> Optional[ChatSession]:
        key = self._make_key(user_id, interface, session_id)
        with self._lock:
            session = self._sessions.get(key)
            if session is not None:
                session.touch()
            return session

    def remove(self, user_id: Any, interface: Any, session_id: Any = "default") -> bool:
        key = self._make_key(user_id, interface, session_id)
        with self._lock:
            return self._sessions.pop(key, None) is not None

    def size(self) -> int:
        with self._lock:
            return len(self._sessions)

    def list_keys(self) -> List[SessionKey]:
        with self._lock:
            return list(self._sessions.keys())

    def list_sessions(self) -> List[ChatSession]:
        with self._lock:
            return list(self._sessions.values())

    def remove_key(self, key: SessionKey) -> bool:
        with self._lock:
            return self._sessions.pop(key, None) is not None
