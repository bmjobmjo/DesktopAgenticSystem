"""Normalized inbound request envelope for conversation processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class InboundRequest:
    conversation_id: str
    interface: str
    user_id: str
    message: str
    files: list[str] = field(default_factory=list)
    execution_metadata: dict[str, Any] = field(default_factory=dict)
    ui_callback: Optional[Callable[[dict[str, Any]], None]] = None
    status_callback: Optional[Callable[[str], None]] = None
    trace_callback: Optional[Callable[[str, dict[str, Any]], None]] = None
    permission_callback: Optional[Callable[[str, dict[str, Any]], bool]] = None
    completion_callback: Optional[Callable[[Any], None]] = None
