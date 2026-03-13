"""Conversation runtime container."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock

from core.controller import Controller
from core.conversation_context import ConversationContext
from core.executor import Executor
from core.router import Router


@dataclass
class ConversationRuntime:
    conversation_id: str
    interface: str
    user_id: str
    cda: ConversationContext
    router: Router
    executor: Executor
    controller: Controller
    pending: deque = field(default_factory=deque)
    lock: RLock = field(default_factory=RLock)
    running: bool = False
    last_access_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.last_access_utc = datetime.now(timezone.utc)
