"""Tools for sending outbound WhatsApp messages/files through folder bridge."""

from __future__ import annotations

__tool_exports__ = ["send_whatsapp_message", "send_whatsapp_file"]

import re
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


def _normalize_mobile(value: str) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _normalize_channel(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    if "@lid" in low:
        return low
    return _normalize_mobile(raw)


def _resolve_mobile(
    recipient_mobile: Optional[str],
    recipient: Optional[str],
    mobile: Optional[str],
    chat_id: Optional[str],
    user_id: Optional[str],
    cda: CommonDataArea,
) -> str:
    explicit_raw = str(recipient_mobile or recipient or mobile or chat_id or "").strip()
    explicit = _normalize_channel(explicit_raw)
    uid = str(user_id or "").strip()

    # Robust detection for database user ID passed as recipient
    if explicit_raw.isdigit() and len(explicit_raw) <= 5:
        uid = explicit_raw

    if not uid:
        uid = str(cda.get_setting("current_user_id") or "").strip()
    if not uid:
        prompt_ctx = cda.get_memory("prompt_context_dict") or {}
        if isinstance(prompt_ctx, dict):
            uid = str(prompt_ctx.get("UID") or "").strip()

    # Avoid treating default placeholder numbers from registry examples/docs as explicit numbers
    placeholders = {"123456789", "1234567890", "919876543210"}
    is_placeholder = explicit in placeholders or explicit_raw in placeholders

    # Direct DB search for 10-digit numbers to promote them to fully-qualified registered WhatsapID
    if explicit and len(explicit) <= 10 and not is_placeholder:
        db_file = _db_path(cda)
        try:
            conn = sqlite3.connect(str(db_file))
            cur = conn.cursor()
            
            cur.execute("PRAGMA table_info(Users)")
            ucols = {str(r[1]) for r in cur.fetchall()}
            if "id" in ucols:
                candidate_search_cols = [c for c in ("WhatsapID", "whatsapp_number", "mobile_number") if c in ucols]
                for col in candidate_search_cols:
                    cur.execute(f"SELECT WhatsapID, whatsapp_number, mobile_number FROM Users WHERE {col} LIKE ?", (f"%{explicit}",))
                    for row in cur.fetchall():
                        for val in row:
                            mapped = _normalize_channel(str(val or ""))
                            if mapped and 10 <= len(mapped) <= 15:
                                conn.close()
                                return mapped
                                
            cur.execute("PRAGMA table_info(Employees)")
            ecols = {str(r[1]) for r in cur.fetchall()}
            if "mobile_number" in ecols and "linked_user_id" in ecols:
                cur.execute("SELECT linked_user_id FROM Employees WHERE mobile_number LIKE ?", (f"%{explicit}",))
                row = cur.fetchone()
                if row and row[0]:
                    linked_uid = str(row[0]).strip()
                    if "WhatsapID" in ucols:
                        cur.execute("SELECT WhatsapID FROM Users WHERE id=? LIMIT 1", (linked_uid,))
                        urow = cur.fetchone()
                        if urow:
                            mapped = _normalize_channel(str(urow[0] or ""))
                            if mapped:
                                conn.close()
                                return mapped
                    for col in ("whatsapp_number", "mobile_number"):
                        if col in ucols:
                            cur.execute(f"SELECT {col} FROM Users WHERE id=? LIMIT 1", (linked_uid,))
                            urow = cur.fetchone()
                            if urow:
                                mapped = _normalize_mobile(str(urow[0] or ""))
                                if mapped and 10 <= len(mapped) <= 15:
                                    conn.close()
                                    return mapped
            conn.close()
        except Exception:
            pass

    explicit_looks_like_user_id = bool(explicit and uid and explicit == uid)
    if explicit and not explicit_looks_like_user_id and not is_placeholder:
        # If the number is a local number without country code (length <= 10),
        # allow falling through to database lookup to find the fully qualified WhatsapID.
        if len(explicit) <= 10 and uid:
            pass
        else:
            return explicit

    if not uid:
        return ""

    db_file = _db_path(cda)
    conn = sqlite3.connect(str(db_file))
    try:
        cur = conn.cursor()

        cur.execute("PRAGMA table_info(Users)")
        ucols = {str(r[1]) for r in cur.fetchall()}

        if "id" in ucols:
            if "WhatsapID" in ucols:
                cur.execute("SELECT WhatsapID FROM Users WHERE id=? LIMIT 1", (uid,))
                row = cur.fetchone()
                if row:
                    mapped = _normalize_channel(str(row[0] or ""))
                    if mapped:
                        return mapped

            candidate_cols = [
                c for c in ("whatsapp_number", "whatsapnumber", "whatsappnumber", "mobile_number") if c in ucols
            ]
            if candidate_cols:
                cur.execute(f"SELECT {', '.join(candidate_cols)} FROM Users WHERE id=? LIMIT 1", (uid,))
                row = cur.fetchone()
                if row:
                    for value in row:
                        mapped = _normalize_mobile(str(value or ""))
                        if mapped and 10 <= len(mapped) <= 15:
                            return mapped

        cur.execute("PRAGMA table_info(ChannelUsers)")
        ccols = {str(r[1]) for r in cur.fetchall()}

        if {"provider", "channel_user_id", "user_id"}.issubset(ccols):
            cur.execute(
                """
                SELECT channel_user_id
                FROM ChannelUsers
                WHERE provider=? AND user_id=?
                ORDER BY updated_at DESC
                """,
                ("whatsapp", uid),
            )
            rows = cur.fetchall()
            for row in rows:
                raw = str((row or [""])[0] or "")
                mapped = _normalize_channel(raw)
                if mapped:
                    return mapped
    except Exception:
        pass
    finally:
        conn.close()

    return ""


def send_whatsapp_message(
    message: str,
    recipient_mobile: str = "",
    recipient: str = "",
    mobile: str = "",
    chat_id: str = "",
    user_id: str = "",
) -> Dict[str, Any]:
    cda = CommonDataArea()
    svc = cda.get_runtime("whatsapp_folder_service")
    if svc is None:
        return {"success": False, "error": "WhatsApp folder service is not running."}

    target_mobile = _resolve_mobile(recipient_mobile, recipient, mobile, chat_id, user_id, cda)
    if not target_mobile:
        return {
            "success": False,
            "error": "No WhatsApp recipient resolved. Provide recipient_mobile/mobile or mapped user_id.",
        }

    result = svc.send_text(target_mobile, str(message or ""))
    ok = bool(result.get("ok", False))
    return {
        "success": ok,
        "recipient_mobile": target_mobile,
        "result": result,
    }


def send_whatsapp_file(
    file_path: str,
    caption: str = "",
    recipient_mobile: str = "",
    recipient: str = "",
    mobile: str = "",
    chat_id: str = "",
    user_id: str = "",
) -> Dict[str, Any]:
    cda = CommonDataArea()
    svc = cda.get_runtime("whatsapp_folder_service")
    if svc is None:
        return {"success": False, "error": "WhatsApp folder service is not running."}

    target_mobile = _resolve_mobile(recipient_mobile, recipient, mobile, chat_id, user_id, cda)
    if not target_mobile:
        return {
            "success": False,
            "error": "No WhatsApp recipient resolved. Provide recipient_mobile/mobile or mapped user_id.",
        }

    result = svc.send_file(target_mobile, file_path=file_path, caption=caption or "")
    ok = bool(result.get("ok", False))
    return {
        "success": ok,
        "recipient_mobile": target_mobile,
        "file_path": str(file_path),
        "result": result,
    }
