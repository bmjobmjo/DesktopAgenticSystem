"""Telegram identity and message controller."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, List, Optional

from core.common_data_area import CommonDataArea
from core.inbound_request import InboundRequest
from execution_logger import log_exception, log_execution_step
from telagram_gateways.telegram_log import telegram_log


class TelegramController:
    def __init__(
        self,
        cda: CommonDataArea,
        controller: Any | None = None,
        conversation_manager: Any | None = None,
    ) -> None:
        self.cda = cda
        self.controller = controller
        self.conversation_manager = conversation_manager
        self._pending_email_by_chat: set[str] = set()

    def _db_path(self) -> Path:
        return Path(str(self.cda.get_setting("sqlite_db_path", "backend.db") or "backend.db")).resolve()

    @staticmethod
    def _normalize_chat_id(chat_id: str) -> str:
        return str(chat_id or "").strip()

    @staticmethod
    def _is_valid_email(value: str) -> bool:
        return bool(re.match(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$", str(value or "").strip()))

    def _ensure_telegram_chat_column(self) -> None:
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            cols = {str(r[1]) for r in cur.fetchall()}
            if "telegram_chat_id" not in cols:
                cur.execute("ALTER TABLE Users ADD COLUMN telegram_chat_id TEXT")
                conn.commit()
        finally:
            conn.close()

    def _find_user_id_by_telegram_chat_id(self, chat_id: str) -> str:
        chat_id = self._normalize_chat_id(chat_id)
        if not chat_id:
            return ""
        self._ensure_telegram_chat_column()

        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM Users WHERE telegram_chat_id = ? LIMIT 1", (chat_id,))
            row = cur.fetchone()
            if row and row[0] is not None:
                return str(row[0])
            return ""
        finally:
            conn.close()

    def _find_user_id_by_channel_mapping(self, chat_id: str) -> str:
        chat_id = self._normalize_chat_id(chat_id)
        if not chat_id:
            return ""
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT user_id FROM ChannelUsers WHERE provider=? AND channel_user_id=? LIMIT 1",
                ("telegram", chat_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0])
            return ""
        finally:
            conn.close()

    def _find_user_by_email(self, email: str) -> tuple[str, str]:
        email = str(email or "").strip().lower()
        if not email:
            return "", ""
        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(Users)")
            cols = {str(r[1]) for r in cur.fetchall()}
            if "email" not in cols or "id" not in cols:
                return "", ""
            display_col = "username" if "username" in cols else ("full_name" if "full_name" in cols else "id")
            cur.execute(f"SELECT id, {display_col} FROM Users WHERE LOWER(email)=LOWER(?) LIMIT 1", (email,))
            row = cur.fetchone()
            if row and row[0] is not None:
                return str(row[0]), str(row[1] or "")
            return "", ""
        finally:
            conn.close()

    def _bind_chat_to_user(self, chat_id: str, user_id: str) -> None:
        chat_id = self._normalize_chat_id(chat_id)
        user_id = str(user_id or "").strip()
        if not chat_id or not user_id:
            return
        self._ensure_telegram_chat_column()

        conn = sqlite3.connect(str(self._db_path()))
        try:
            cur = conn.cursor()
            cur.execute("UPDATE Users SET telegram_chat_id=? WHERE id=?", (chat_id, user_id))
            cur.execute(
                """
                INSERT INTO ChannelUsers (provider, channel_user_id, user_id)
                VALUES (?, ?, ?)
                ON CONFLICT(provider, channel_user_id)
                DO UPDATE SET user_id=excluded.user_id, updated_at=CURRENT_TIMESTAMP
                """,
                ("telegram", chat_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _dispatch_to_main_controller(
        self,
        user_id: str,
        chat_id: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
    ) -> str:
        if self.controller is None:
            return ""
        telegram_log(
            "controller_dispatch",
            f"user_id={user_id} chat_id={chat_id} text_len={len(text)} file_count={len(files or [])}",
        )
        result = self.controller.handle_user_message(
            text,
            files=files,
            interface="Telegram",
            user_id=user_id,
            channel_id=chat_id,
            session_id=f"telegram:{chat_id}",
            ui_callback=ui_callback,
        )
        return str(getattr(result, "content", "") or "").strip()

    def _submit_to_conversation_manager(
        self,
        user_id: str,
        chat_id: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
        completion_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        if self.conversation_manager is None:
            return self._dispatch_to_main_controller(user_id, chat_id, text, files=files, ui_callback=ui_callback)

        telegram_log(
            "conversation_submit",
            f"user_id={user_id} chat_id={chat_id} text_len={len(text)} file_count={len(files or [])}",
        )

        def _complete(result: Any) -> None:
            if not callable(completion_callback):
                return
            text_out = str(getattr(result, "content", "") or "").strip()
            completion_callback(text_out)

        request = InboundRequest(
            conversation_id=f"telegram:{chat_id}",
            interface="Telegram",
            user_id=user_id,
            message=text,
            files=list(files or []),
            ui_callback=ui_callback,
            completion_callback=_complete,
        )
        self.conversation_manager.submit(request)
        return ""

    def handle_inbound_text(
        self,
        chat_id: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
        completion_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        chat_id = self._normalize_chat_id(chat_id)
        text = str(text or "").strip()
        if not chat_id or (not text and not files):
            return ""

        user_id = self._find_user_id_by_telegram_chat_id(chat_id)
        if not user_id:
            user_id = self._find_user_id_by_channel_mapping(chat_id)
            if user_id:
                self._bind_chat_to_user(chat_id, user_id)

        if user_id:
            telegram_log("chat_verified", f"chat_id={chat_id} user_id={user_id} source=telegram_chat_id_or_mapping")
            return self._submit_to_conversation_manager(
                user_id,
                chat_id,
                text,
                files=files,
                ui_callback=ui_callback,
                completion_callback=completion_callback,
            )

        if chat_id in self._pending_email_by_chat:
            if not self._is_valid_email(text):
                telegram_log("email_invalid", f"chat_id={chat_id}")
                return "Please provide a valid email ID to continue."

            resolved_user_id, display_name = self._find_user_by_email(text)
            if not resolved_user_id:
                telegram_log("email_not_found", f"chat_id={chat_id}")
                return "Email ID not found. Please try again with your registered email."

            self._bind_chat_to_user(chat_id, resolved_user_id)
            self._pending_email_by_chat.discard(chat_id)
            telegram_log("email_verified", f"chat_id={chat_id} user_id={resolved_user_id}")
            greeting_name = display_name or f"User {resolved_user_id}"
            return f"Welcome {greeting_name}. Your Telegram chat is now linked. You can continue chatting."

        self._pending_email_by_chat.add(chat_id)
        log_execution_step("TELEGRAM_AUTH", f"Email verification requested for chat_id={chat_id}")
        telegram_log("email_requested", f"chat_id={chat_id}")
        return "Please provide your registered email ID to verify your account."

    def handle_inbound_safe(
        self,
        chat_id: str,
        text: str,
        files: List[str] | None = None,
        ui_callback=None,
        completion_callback: Optional[Callable[[str], None]] = None,
    ) -> str:
        try:
            response = self.handle_inbound_text(
                chat_id,
                text,
                files=files,
                ui_callback=ui_callback,
                completion_callback=completion_callback,
            )
            if "Session lock timeout" in response:
                return "Previous Telegram request is still processing. Please wait a moment and try again."
            return response
        except Exception as exc:
            log_exception("TELEGRAM_CONTROLLER_ERROR", exc, {"chat_id": chat_id, "files": files or []})
            telegram_log("controller_error", f"chat_id={chat_id} error={exc}")
            return "Sorry, I hit an internal error. Please try again."
