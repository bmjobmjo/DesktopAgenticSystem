"""WhatsApp identity and message controller for shared-folder bridge."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, List, Optional

from core.channel_commands import NEW_SESSION_RESET_MESSAGE, is_new_session_command
from core.common_data_area import CommonDataArea
from core.inbound_request import InboundRequest
from execution_logger import log_exception
from whatsapp_gateways.whatsapp_log import whatsapp_log


class WhatsAppController:
    def __init__(
        self,
        cda: CommonDataArea,
        controller: Any | None = None,
        conversation_manager: Any | None = None,
    ) -> None:
        self.cda = cda
        self.controller = controller
        self.conversation_manager = conversation_manager

    def _db_path(self) -> Path:
        return Path(str(self.cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()

    def _db_connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path()), timeout=20)
        conn.execute("PRAGMA busy_timeout = 20000")
        return conn

    @staticmethod
    def normalize_mobile(value: str) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    def normalize_channel_id(value: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        low = raw.lower()
        if "@lid" in low:
            return low
        return re.sub(r"\D+", "", raw)

    def _find_user_id_by_channel_mapping(self, sender_channel_id: str) -> str:
        sender_channel_id = self.normalize_channel_id(sender_channel_id)
        if not sender_channel_id:
            return ""
        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id FROM ChannelUsers WHERE provider=? AND channel_user_id=? LIMIT 1",
                ("whatsapp", sender_channel_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0])
            return ""
        except sqlite3.OperationalError:
            return ""
        finally:
            conn.close()

    def _find_user_id_by_mobile_number(self, sender_mobile: str) -> str:
        sender_mobile = self.normalize_mobile(sender_mobile)
        if not sender_mobile:
            return ""

        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            cols = {str(r[1]) for r in cur.fetchall()}
            if "id" not in cols:
                return ""

            candidate_cols = [c for c in ("whatsapp_number", "whatsapnumber", "whatsappnumber", "mobile_number") if c in cols]
            if not candidate_cols:
                return ""

            select_cols = ", ".join(candidate_cols)
            cur.execute(f"SELECT id, {select_cols} FROM Users")
            for row in cur.fetchall():
                uid = str(row[0] or "").strip()
                if not uid:
                    continue
                for value in row[1:]:
                    mobile = self.normalize_mobile(str(value or ""))
                    if mobile and mobile == sender_mobile:
                        return uid
            return ""
        finally:
            conn.close()

    def _bind_channel_to_user(self, sender_channel_id: str, user_id: str) -> None:
        sender_channel_id = self.normalize_channel_id(sender_channel_id)
        user_id = str(user_id or "").strip()
        if not sender_channel_id or not user_id:
            return
        conn = self._db_connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ChannelUsers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    channel_user_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, channel_user_id)
                )
                """
            )
            try:
                cur.execute(
                    """
                    INSERT INTO ChannelUsers (provider, channel_user_id, user_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(provider, channel_user_id)
                    DO UPDATE SET user_id=excluded.user_id, updated_at=CURRENT_TIMESTAMP
                    """,
                    ("whatsapp", sender_channel_id, user_id),
                )
            except sqlite3.OperationalError:
                cur.execute(
                    "UPDATE ChannelUsers SET user_id=?, updated_at=CURRENT_TIMESTAMP WHERE provider=? AND channel_user_id=?",
                    (user_id, "whatsapp", sender_channel_id),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        "INSERT INTO ChannelUsers (provider, channel_user_id, user_id) VALUES (?, ?, ?)",
                        ("whatsapp", sender_channel_id, user_id),
                    )
            conn.commit()
        finally:
            conn.close()

    def _dispatch_to_main_controller(
        self,
        user_id: str,
        sender_channel_id: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
    ) -> str:
        if self.controller is None:
            return ""
        result = self.controller.handle_user_message(
            text,
            files=files,
            interface="WhatsApp",
            user_id=user_id,
            channel_id=sender_channel_id,
            session_id=f"whatsapp:{sender_channel_id}",
            ui_callback=ui_callback,
        )
        return str(getattr(result, "content", "") or "").strip()

    def _submit_to_conversation_manager(
        self,
        user_id: str,
        sender_channel_id: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
        completion_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        if self.conversation_manager is None:
            return self._dispatch_to_main_controller(user_id, sender_channel_id, text, files=files, ui_callback=ui_callback)

        def _complete(result: Any) -> None:
            if not callable(completion_callback):
                return
            text_out = str(getattr(result, "content", "") or "").strip()
            completion_callback(text_out)

        request = InboundRequest(
            conversation_id=f"whatsapp:{sender_channel_id}",
            interface="WhatsApp",
            user_id=user_id,
            message=text,
            files=list(files or []),
            ui_callback=ui_callback,
            completion_callback=_complete,
        )
        self.conversation_manager.submit(request)
        return ""

    def _reset_channel_session(self, sender_channel_id: str, user_id: str = "") -> None:
        session_id = f"whatsapp:{sender_channel_id}"
        if self.conversation_manager is not None:
            self.conversation_manager.reset_conversation(
                session_id,
                interface="WhatsApp",
                user_id=str(user_id or "").strip() or None,
            )
            return
        if self.controller is not None:
            self.controller.reset_session_state(
                interface="WhatsApp",
                user_id=str(user_id or "").strip() or None,
                session_id=session_id,
            )

    def handle_inbound_text(
        self,
        sender_channel_id: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
        completion_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        sender_channel_id = self.normalize_channel_id(sender_channel_id)
        sender_mobile = self.normalize_mobile(sender_channel_id)
        raw_text = str(text or "")
        reset_requested = not files and is_new_session_command(raw_text)
        text = raw_text.strip()
        if not sender_channel_id or (not text and not files):
            return ""

        user_id = self._find_user_id_by_channel_mapping(sender_channel_id)
        if not user_id and sender_mobile:
            user_id = self._find_user_id_by_mobile_number(sender_mobile)
            if user_id:
                self._bind_channel_to_user(sender_channel_id, user_id)

        if reset_requested:
            self._reset_channel_session(sender_channel_id, user_id=user_id)
            return NEW_SESSION_RESET_MESSAGE

        if not user_id:
            whatsapp_log("unknown_sender", f"channel_id={sender_channel_id}")
            return "Your WhatsApp number is not registered in this system."

        return self._submit_to_conversation_manager(
            user_id,
            sender_channel_id,
            text,
            files=files,
            ui_callback=ui_callback,
            completion_callback=completion_callback,
        )

    def handle_inbound_safe(
        self,
        sender_mobile: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
        completion_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        try:
            response = self.handle_inbound_text(
                sender_mobile,
                text,
                files=files,
                ui_callback=ui_callback,
                completion_callback=completion_callback,
            )
            if "Session lock timeout" in response:
                return "Previous WhatsApp request is still processing. Please wait a moment and try again."
            return response
        except Exception as exc:
            log_exception("WHATSAPP_CONTROLLER_ERROR", exc, {"sender_mobile": sender_mobile, "files": files or []})
            whatsapp_log("controller_error", f"mobile={sender_mobile} error={exc}")
            return "Sorry, I hit an internal error. Please try again."



