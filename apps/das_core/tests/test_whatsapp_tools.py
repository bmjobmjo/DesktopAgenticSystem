from __future__ import annotations

import sqlite3

from core.common_data_area import CommonDataArea
from tools.whatsapp_tools import send_whatsapp_file, send_whatsapp_message


class _DummyWhatsAppService:
    def __init__(self) -> None:
        self.last_text = None
        self.last_file = None

    def send_text(self, recipient_mobile: str, text: str):
        self.last_text = (recipient_mobile, text)
        return {"ok": True, "message_id": "m1"}

    def send_file(self, recipient_mobile: str, file_path: str, caption: str = ""):
        self.last_file = (recipient_mobile, file_path, caption)
        return {"ok": True, "message_id": "m2", "path": "dummy"}


def test_send_whatsapp_message_direct_mobile_uses_folder_service() -> None:
    cda = CommonDataArea()
    cda.reset()
    svc = _DummyWhatsAppService()
    cda.set_runtime("whatsapp_folder_service", svc)

    result = send_whatsapp_message("hello", recipient_mobile="+91 98765 43210")

    assert result["success"] is True
    assert result["recipient_mobile"] == "919876543210"
    assert svc.last_text == ("919876543210", "hello")


def test_send_whatsapp_file_resolves_mobile_by_user_mapping(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)"
        )
        cur.execute(
            "INSERT INTO ChannelUsers (provider, channel_user_id, user_id) VALUES (?, ?, ?)",
            ("whatsapp", "919998887777", "7"),
        )
        conn.commit()
    finally:
        conn.close()

    source = tmp_path / "report.txt"
    source.write_text("report", encoding="utf-8")

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    svc = _DummyWhatsAppService()
    cda.set_runtime("whatsapp_folder_service", svc)

    result = send_whatsapp_file(file_path=str(source), caption="latest", user_id="7")

    assert result["success"] is True
    assert result["recipient_mobile"] == "919998887777"
    assert svc.last_file == ("919998887777", str(source), "latest")


def test_send_whatsapp_message_prefers_users_whatsapp_number_over_lid_mapping(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)"
        )
        cur.execute(
            "INSERT INTO ChannelUsers (provider, channel_user_id, user_id, updated_at) VALUES (?, ?, ?, ?)",
            ("whatsapp", "108636919619752@lid", "1", "2026-03-20 12:00:00"),
        )
        cur.execute(
            "CREATE TABLE Users (id INTEGER PRIMARY KEY, whatsapp_number TEXT, mobile_number TEXT)"
        )
        cur.execute(
            "INSERT INTO Users (id, whatsapp_number, mobile_number) VALUES (?, ?, ?)",
            (1, "917511120971", "7511120971"),
        )
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    svc = _DummyWhatsAppService()
    cda.set_runtime("whatsapp_folder_service", svc)

    result = send_whatsapp_message("hi", user_id="1")

    assert result["success"] is True
    assert result["recipient_mobile"] == "917511120971"
    assert svc.last_text == ("917511120971", "hi")
