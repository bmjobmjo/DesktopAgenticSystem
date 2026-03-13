from __future__ import annotations
import sqlite3

from pathlib import Path

from core.common_data_area import CommonDataArea
from telagram_gateways.telegram_service import TelegramChannelService


class _DummyController:
    controller = None


class _DummyResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_DummyResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_download_telegram_file_uses_default_directory(tmp_path, monkeypatch):
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("default_directory", str(tmp_path))
    cda.set_setting("telegram_bot_token", "token")

    service = TelegramChannelService(cda=cda, telegram_controller=_DummyController())

    def fake_get_json(url: str, timeout: int):
        return {"ok": True, "result": {"file_path": "photos/receipt.jpg"}}

    monkeypatch.setattr(service, "_http_get_json", fake_get_json)
    monkeypatch.setattr(
        "telagram_gateways.telegram_service.urlrequest.urlopen",
        lambda req, timeout=60: _DummyResponse(b"fake-image-bytes"),
    )

    saved_path = Path(service._download_telegram_file("file-123", "telegram_photo.jpg", "8307703708"))

    assert saved_path.exists()
    assert saved_path.parent == tmp_path / "telegram_inbound" / "8307703708"
    assert saved_path.read_bytes() == b"fake-image-bytes"


def test_poll_loop_skips_duplicate_update_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE ChannelInboundMessages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                message_id TEXT NOT NULL,
                received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                handled INTEGER DEFAULT 0,
                UNIQUE(provider, message_id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    service = TelegramChannelService(cda=cda, telegram_controller=_DummyController())

    update = {"update_id": 68932079, "message": {"chat": {"id": 6418599489}, "text": "/new"}}
    send_calls = []
    process_calls = []

    def fake_get_updates():
        service._stop_event.set()
        return [update, update]

    monkeypatch.setattr(service, "_get_updates", fake_get_updates)
    monkeypatch.setattr(service, "_extract_inbound_payload", lambda upd: ("6418599489", "/new", []))
    monkeypatch.setattr(service, "send_text", lambda chat_id, text: send_calls.append((chat_id, text)) or {"ok": True})
    monkeypatch.setattr(
        service,
        "_process_inbound_message",
        lambda chat_id, text, files=None: process_calls.append((chat_id, text, tuple(files or []))),
    )

    service._poll_loop()

    assert send_calls == [("6418599489", "Message received. Working on it...")]
    assert process_calls == [("6418599489", "/new", ())]

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT provider, message_id, handled FROM ChannelInboundMessages ORDER BY id"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    assert rows == [("telegram", "68932079", 1)]
