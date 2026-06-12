"""Tools for sending outbound Telegram messages/files."""

from __future__ import annotations

__tool_exports__ = ['send_telegram_message', 'send_telegram_file']

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from core.common_data_area import CommonDataArea


def _db_path(cda: CommonDataArea) -> Path:
    # 1. Try sqlite_db_path from settings
    path_str = cda.get_setting("sqlite_db_path")
    if path_str:
        p = Path(str(path_str)).resolve()
        if p.exists() and p.is_file():
            # Check if this database has a Users table
            try:
                import sqlite3
                conn = sqlite3.connect(str(p))
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Users'")
                has_users = bool(cur.fetchone())
                conn.close()
                if has_users:
                    return p
            except Exception:
                pass

    # 2. Check sibling path of __file__ up 3 levels to "data/office_automation.db"
    try:
        p_fallback = Path(__file__).resolve().parent.parent.parent / "data" / "office_automation.db"
        if p_fallback.exists() and p_fallback.is_file():
            return p_fallback
    except Exception:
        pass

    # 3. Check relative path from CWD looking upward
    try:
        for rel in ("data/office_automation.db", "../data/office_automation.db", "../../data/office_automation.db"):
            p_cwd = Path(rel).resolve()
            if p_cwd.exists() and p_cwd.is_file():
                return p_cwd
    except Exception:
        pass

    # 4. Fallback to default setting or backend.db
    return Path(str(cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()


def _resolve_chat_id(chat_id: Optional[str], user_id: Optional[str], cda: CommonDataArea) -> str:
    explicit = str(chat_id or "").strip()
    uid = str(user_id or "").strip()

    # Robust detection for database user ID passed as chat_id
    if explicit.isdigit() and len(explicit) <= 5:
        uid = explicit

    if not uid:
        uid = str(cda.get_setting("current_user_id") or "").strip()
    if not uid:
        prompt_ctx = cda.get_memory("prompt_context_dict") or {}
        if isinstance(prompt_ctx, dict):
            uid = str(prompt_ctx.get("UID") or "").strip()

    # Avoid treating default placeholder values from registry examples/docs as explicit IDs
    placeholders = {"123456789", "1234567890", "919876543210"}
    is_placeholder = explicit in placeholders

    # Some agent/tool calls mistakenly pass the internal user id as chat_id.
    # When both values match, prefer resolving the real Telegram channel mapping.
    explicit_looks_like_user_id = bool(explicit and uid and explicit == uid)
    if explicit and not explicit_looks_like_user_id and not is_placeholder:
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

