"""Lightweight logger for WhatsApp folder bridge events."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def whatsapp_log(event: str, message: str) -> None:
    try:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "whatsapp_bridge.log"
        line = f"{datetime.now(timezone.utc).isoformat()} [{event}] {message}\n"
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        return
