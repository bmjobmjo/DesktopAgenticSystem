"""Dedicated Telegram channel log writer."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_FILE = LOG_DIR / "telegram_channel.log"


def telegram_log(event: str, message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} [{str(event or '').strip().upper()}] {str(message or '').strip()}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Logging should never block channel flow.
        pass

