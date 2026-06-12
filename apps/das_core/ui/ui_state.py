"""UI state container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.controller import Controller


@dataclass
class UIState:
    controller: Controller
    last_status: Optional[str] = None
