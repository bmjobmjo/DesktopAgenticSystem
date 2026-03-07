"""Tools for sending outbound Telegram messages/files."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from core.common_data_area import CommonDataArea


def _db_path(cda: CommonDataArea) -> Path:
    return Path(str(cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()


def _resolve_chat_id(chat_id: Optional[str], user_id: Optional[str], cda: CommonDataArea) -> str:
    explicit = str(chat_id or "").strip()
    uid = str(user_id or "").strip()

    # Some agent/tool calls mistakenly pass the internal user id as chat_id.
    # When both values match, prefer resolving the real Telegram channel mapping.
    explicit_looks_like_user_id = bool(explicit and uid and explicit == uid)
    if explicit and not explicit_looks_like_user_id:
        return explicit

    if not uid:
        return str(cda.get_setting("telegram_test_chat_id", "") or "").strip()

    conn = sqlite3.connect(str(_db_path(cda)))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(Users)")
        ucols = {str(r[1]) for r in cur.fetchall()}
        if "telegram_chat_id" in ucols:
            cur.execute("SELECT telegram_chat_id FROM Users WHERE id=? LIMIT 1", (uid,))
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0]).strip()

        cur.execute("PRAGMA table_info(ChannelUsers)")
        ccols = {str(r[1]) for r in cur.fetchall()}
        if {"provider", "channel_user_id", "user_id"}.issubset(ccols):
            cur.execute(
                "SELECT channel_user_id FROM ChannelUsers WHERE provider=? AND user_id=? LIMIT 1",
                ("telegram", uid),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0]).strip()
    finally:
        conn.close()

    return ""


def send_telegram_message(message: str, chat_id: str = "", user_id: str = "") -> Dict[str, Any]:
    """
    Send a text message to Telegram via running TelegramChannelService.

    Args:
        message: Message text to send.
        chat_id: Telegram chat id (preferred if known).
        user_id: Internal user id; resolves mapped Telegram chat if chat_id is omitted.
    """
    cda = CommonDataArea()
    svc = cda.get_runtime("telegram_channel_service")
    if svc is None:
        return {"success": False, "error": "Telegram channel service is not running."}

    target_chat_id = _resolve_chat_id(chat_id, user_id, cda)
    if not target_chat_id:
        return {"success": False, "error": "No Telegram chat_id resolved. Provide chat_id or mapped user_id."}

    result = svc.send_text(target_chat_id, str(message or ""))
    ok = bool(result.get("ok", False))
    return {
        "success": ok,
        "chat_id": target_chat_id,
        "result": result,
    }


def send_telegram_file(file_path: str, caption: str = "", chat_id: str = "", user_id: str = "") -> Dict[str, Any]:
    """
    Send a file/document to Telegram via running TelegramChannelService.

    Args:
        file_path: Absolute/local path to the file.
        caption: Optional caption text.
        chat_id: Telegram chat id (preferred if known).
        user_id: Internal user id; resolves mapped Telegram chat if chat_id is omitted.
    """
    cda = CommonDataArea()
    svc = cda.get_runtime("telegram_channel_service")
    if svc is None:
        return {"success": False, "error": "Telegram channel service is not running."}

    target_chat_id = _resolve_chat_id(chat_id, user_id, cda)
    if not target_chat_id:
        return {"success": False, "error": "No Telegram chat_id resolved. Provide chat_id or mapped user_id."}

    result = svc.send_document(target_chat_id, file_path=file_path, caption=caption or "")
    ok = bool(result.get("ok", False))
    return {
        "success": ok,
        "chat_id": target_chat_id,
        "file_path": str(file_path),
        "result": result,
    }

