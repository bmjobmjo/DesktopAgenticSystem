"""Runtime bootstrap helpers for API gateway."""

from __future__ import annotations

import atexit
import logging as _stdlib_logging
import sys
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Tuple

sys.modules.setdefault("logging", _stdlib_logging)

_ROOT = Path(__file__).resolve().parents[2]
_DAS_CORE_ROOT = _ROOT / "apps" / "das_core"
if str(_DAS_CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(_DAS_CORE_ROOT))


class RuntimeRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._runtime: Dict[str, Any] = {}

    def get_or_init(self) -> Tuple[Any, Any]:
        with self._lock:
            cda = self._runtime.get("cda")
            conversation_manager = self._runtime.get("conversation_manager")
            if cda is not None and conversation_manager is not None:
                return cda, conversation_manager

            from core.db_schema import init_db
            from app_bootstrap import build_application

            init_db()
            cda, conversation_manager = build_application()
            self._runtime["cda"] = cda
            self._runtime["conversation_manager"] = conversation_manager
            return cda, conversation_manager

    def shutdown(self) -> None:
        with self._lock:
            cda = self._runtime.get("cda")
            conversation_manager = self._runtime.get("conversation_manager")
            self._runtime.clear()

        if cda is None or conversation_manager is None:
            return

        try:
            tg_service = cda.get_runtime("telegram_channel_service")
            if tg_service:
                tg_service.stop()
                cda.set_runtime("telegram_channel_service", None)
        except Exception:
            pass

        try:
            wa_service = cda.get_runtime("whatsapp_folder_service")
            if wa_service:
                wa_service.stop()
                cda.set_runtime("whatsapp_folder_service", None)
        except Exception:
            pass

        try:
            wa_headless = cda.get_runtime("whatsapp_headless_bridge_service")
            if wa_headless:
                wa_headless.stop_all()
                cda.set_runtime("whatsapp_headless_bridge_service", None)
        except Exception:
            pass

        try:
            scheduler_service = cda.get_runtime("scheduler_service")
            if scheduler_service:
                scheduler_service.stop()
                cda.set_runtime("scheduler_service", None)
        except Exception:
            pass

        try:
            conversation_manager.shutdown()
        except Exception:
            pass


registry = RuntimeRegistry()
atexit.register(registry.shutdown)
