from __future__ import annotations

import sqlite3
from pathlib import Path

from core.common_data_area import CommonDataArea
from whatsapp_gateways.whatsapp_service import WhatsAppFolderService


class _DummyController:
    mapped_user_id = ""
    mapped_mobile_user_id = ""
    last_bound = None

    @staticmethod
    def normalize_mobile(value: str) -> str:
        import re

        return re.sub(r"\D+", "", str(value or ""))

    @classmethod
    def _find_user_id_by_channel_mapping(cls, sender_id: str) -> str:
        return str(cls.mapped_user_id or "")

    @classmethod
    def _find_user_id_by_mobile_number(cls, sender_mobile: str) -> str:
        return str(cls.mapped_mobile_user_id or "")

    @classmethod
    def _bind_channel_to_user(cls, sender_channel_id: str, user_id: str) -> None:
        cls.last_bound = (str(sender_channel_id), str(user_id))

    @staticmethod
    def handle_inbound_safe(sender_mobile: str, text: str, files=None, ui_callback=None, completion_callback=None) -> str:
        if str(text or "").strip().lower() == "/new":
            return "Started a new chat session. Previous session context cleared."
        return ""


def test_whatsapp_send_text_creates_outbound_folder_structure(tmp_path) -> None:
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("whatsapp_folder_root", str(tmp_path))

    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())
    result = service.send_text("+91 98765 43210", "hello from test")

    assert bool(result.get("ok", False))

    send_root = Path(tmp_path) / "send" / "919876543210"
    folders = [p for p in send_root.iterdir() if p.is_dir()]
    assert len(folders) == 1

    msg = (folders[0] / "message.txt").read_text(encoding="utf-8")
    assert msg == "hello from test"


def test_whatsapp_send_file_creates_outbound_with_attachment(tmp_path) -> None:
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("whatsapp_folder_root", str(tmp_path))

    source = tmp_path / "sample_report.txt"
    source.write_text("hello attachment", encoding="utf-8")

    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())
    result = service.send_file("+91 98765 43210", str(source), caption="report attached")

    assert bool(result.get("ok", False))

    send_root = Path(tmp_path) / "send" / "919876543210"
    folders = [p for p in send_root.iterdir() if p.is_dir()]
    assert len(folders) == 1

    msg = (folders[0] / "message.txt").read_text(encoding="utf-8")
    assert msg == "report attached"
    sent_file = folders[0] / "sample_report.txt"
    assert sent_file.exists()
    assert sent_file.read_text(encoding="utf-8") == "hello attachment"


def test_whatsapp_send_text_supports_lid_recipient(tmp_path) -> None:
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("whatsapp_folder_root", str(tmp_path))

    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())
    result = service.send_text("157298915860713@lid", "hello lid")

    assert bool(result.get("ok", False))

    send_root = Path(tmp_path) / "send" / "157298915860713@lid"
    folders = [p for p in send_root.iterdir() if p.is_dir()]
    assert len(folders) == 1

    msg = (folders[0] / "message.txt").read_text(encoding="utf-8")
    assert msg == "hello lid"


def test_registration_binds_whatsap_id(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE Users (id INTEGER PRIMARY KEY, whatsapp_number TEXT)")
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)"
        )
        cur.execute(
            "CREATE TABLE ChannelInboundMessages (provider TEXT, message_id TEXT, handled INTEGER, UNIQUE(provider, message_id))"
        )
        cur.execute("INSERT INTO Users (id, whatsapp_number) VALUES (?, ?)", (1, "917511120971"))
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(tmp_path / "exchange"))

    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    lid = "157298915860713@lid"
    r1 = service._handle_registration_message(lid, "Register")
    assert "share your whatsapp number" in r1.lower()

    r2 = service._handle_registration_message(lid, "917511120971")
    assert "otp sent" in r2.lower()

    otp = service._register_contexts[lid]["otp"]
    r3 = service._handle_registration_message(lid, otp)
    assert "completed" in r3.lower()

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT WhatsapID FROM Users WHERE id=1")
        row = cur.fetchone()
        assert row and row[0] == lid
    finally:
        conn.close()


def test_registration_binds_numeric_channel_id(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE Users (id INTEGER PRIMARY KEY, whatsapp_number TEXT)")
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)"
        )
        cur.execute(
            "CREATE TABLE ChannelInboundMessages (provider TEXT, message_id TEXT, handled INTEGER, UNIQUE(provider, message_id))"
        )
        cur.execute("INSERT INTO Users (id, whatsapp_number) VALUES (?, ?)", (1, "76197115470002"))
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(tmp_path / "exchange"))

    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    sender = "76197115470002"
    assert "share your whatsapp number" in service._handle_registration_message(sender, "Register").lower()
    assert "otp sent" in service._handle_registration_message(sender, "76197115470002").lower()

    otp = service._register_contexts[sender]["otp"]
    assert "completed" in service._handle_registration_message(sender, otp).lower()

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT WhatsapID FROM Users WHERE id=1")
        row = cur.fetchone()
        assert row and row[0] == sender
    finally:
        conn.close()

def test_register_command_accepts_slash_and_backslash(tmp_path) -> None:
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("whatsapp_folder_root", str(tmp_path / "exchange"))
    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    msg1 = service._handle_registration_message("919999999999", "/register")
    assert "share your whatsapp number" in msg1.lower()

    service._register_contexts.pop("919999999999", None)
    msg2 = service._handle_registration_message("919999999999", "\\register")
    assert "share your whatsapp number" in msg2.lower()

def test_menu_and_new_command_handlers(tmp_path) -> None:
    root = tmp_path / "exchange"
    recv = root / "received" / "919876543210"
    msg1 = recv / "m1"
    msg1.mkdir(parents=True, exist_ok=True)
    (msg1 / "message.json").write_text(
        """{
  "protocol": "das.whatsapp.folder/1.0",
  "direction": "inbound",
  "message_id": "m1",
  "provider": "whatsapp",
  "bridge_id": "whatsapp-main",
  "provider_message_id": "pm1",
  "sender_id": "+919876543210",
  "sender_folder": "919876543210",
  "timestamp_utc": "2026-03-23T05:00:00Z",
  "text": "/menu",
  "attachments": []
}""",
        encoding="utf-8",
    )

    msg2 = recv / "m2"
    msg2.mkdir(parents=True, exist_ok=True)
    (msg2 / "message.json").write_text(
        """{
  "protocol": "das.whatsapp.folder/1.0",
  "direction": "inbound",
  "message_id": "m2",
  "provider": "whatsapp",
  "bridge_id": "whatsapp-main",
  "provider_message_id": "pm2",
  "sender_id": "+919876543210",
  "sender_folder": "919876543210",
  "timestamp_utc": "2026-03-23T05:00:01Z",
  "text": "/new",
  "attachments": []
}""",
        encoding="utf-8",
    )

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE ChannelInboundMessages (provider TEXT, message_id TEXT, handled INTEGER, UNIQUE(provider, message_id))")
        cur.execute("CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)")
        conn.commit()
    finally:
        conn.close()

    _DummyController.mapped_user_id = "7"
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(root))
    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    service._process_one_inbound("919876543210", msg1)
    service._process_one_inbound("919876543210", msg2)

    send_root = root / "send" / "919876543210"
    folders = sorted([p for p in send_root.iterdir() if p.is_dir()])
    texts = [(f / "message.txt").read_text(encoding="utf-8") for f in folders]
    assert any("/register" in t and "/new" in t for t in texts)
    assert any("Started a new chat session" in t for t in texts)



def test_resolve_mapped_user_via_lid_reverse_mapping(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE Users (id INTEGER PRIMARY KEY, whatsapp_number TEXT, WhatsapID TEXT)")
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME, UNIQUE(provider, channel_user_id))"
        )
        cur.execute("INSERT INTO Users (id, whatsapp_number) VALUES (?, ?)", (1, "917511120971"))
        conn.commit()
    finally:
        conn.close()

    auth_dir = tmp_path / "auth_session"
    auth_dir.mkdir(parents=True, exist_ok=True)
    (auth_dir / "lid-mapping-76197115470002_reverse.json").write_text('"917511120971"', encoding="utf-8")

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(tmp_path / "exchange"))
    cda.set_setting("whatsapp_headless_auth_session_dir", str(auth_dir))

    _DummyController.mapped_user_id = ""
    _DummyController.mapped_mobile_user_id = "1"
    _DummyController.last_bound = None

    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    payload = {
        "sender_id": "+76197115470002@lid",
        "sender_folder": "76197115470002@lid",
    }
    user_id = service._resolve_mapped_user("76197115470002@lid", payload)

    assert user_id == "1"

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM ChannelUsers WHERE provider='whatsapp' AND channel_user_id='76197115470002@lid'")
        row = cur.fetchone()
        assert row and str(row[0]) == "1"
    finally:
        conn.close()



def test_registration_prefers_lid_even_when_sender_folder_is_mobile(tmp_path) -> None:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE Users (id INTEGER PRIMARY KEY, whatsapp_number TEXT, WhatsapID TEXT)")
        cur.execute(
            "CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME, UNIQUE(provider, channel_user_id))"
        )
        cur.execute(
            "CREATE TABLE ChannelInboundMessages (provider TEXT, message_id TEXT, handled INTEGER, UNIQUE(provider, message_id))"
        )
        cur.execute("INSERT INTO Users (id, whatsapp_number) VALUES (?, ?)", (1, "917511120971"))
        conn.commit()
    finally:
        conn.close()

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(tmp_path / "exchange"))

    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    sender_folder_id = "917511120971"
    payload = {
        "sender_id": "+76197115470002@lid",
        "sender_folder": sender_folder_id,
    }

    assert "share your whatsapp number" in service._handle_registration_message(sender_folder_id, "Register", payload=payload).lower()
    assert "otp sent" in service._handle_registration_message(sender_folder_id, "917511120971", payload=payload).lower()

    otp = service._register_contexts[sender_folder_id]["otp"]
    assert "completed" in service._handle_registration_message(sender_folder_id, otp, payload=payload).lower()

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("SELECT WhatsapID FROM Users WHERE id=1")
        row = cur.fetchone()
        assert row and row[0] == "+76197115470002@lid"

        cur.execute("SELECT user_id FROM ChannelUsers WHERE provider='whatsapp' AND channel_user_id='917511120971'")
        row_mobile = cur.fetchone()
        assert row_mobile and str(row_mobile[0]) == "1"

        cur.execute("SELECT user_id FROM ChannelUsers WHERE provider='whatsapp' AND channel_user_id='+76197115470002@lid'")
        row_lid = cur.fetchone()
        assert row_lid and str(row_lid[0]) == "1"
    finally:
        conn.close()


def test_unregistered_non_greeting_message_is_ignored(tmp_path) -> None:
    root = tmp_path / "exchange"
    recv = root / "received" / "919876543210"
    msg = recv / "m1"
    msg.mkdir(parents=True, exist_ok=True)
    (msg / "message.json").write_text(
        """{
  "protocol": "das.whatsapp.folder/1.0",
  "direction": "inbound",
  "message_id": "m1",
  "provider": "whatsapp",
  "bridge_id": "whatsapp-main",
  "provider_message_id": "pm1",
  "sender_id": "+919876543210",
  "sender_folder": "919876543210",
  "timestamp_utc": "2026-03-23T05:00:00Z",
  "text": "Need price details",
  "attachments": []
}""",
        encoding="utf-8",
    )

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE ChannelInboundMessages (provider TEXT, message_id TEXT, handled INTEGER, UNIQUE(provider, message_id))")
        cur.execute("CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)")
        conn.commit()
    finally:
        conn.close()

    _DummyController.mapped_user_id = ""
    _DummyController.mapped_mobile_user_id = ""
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(root))
    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    service._process_one_inbound("919876543210", msg)

    send_root = root / "send" / "919876543210"
    assert not send_root.exists()


def test_unregistered_hi_gets_registration_hint(tmp_path) -> None:
    root = tmp_path / "exchange"
    recv = root / "received" / "919876543210"
    msg = recv / "m1"
    msg.mkdir(parents=True, exist_ok=True)
    (msg / "message.json").write_text(
        """{
  "protocol": "das.whatsapp.folder/1.0",
  "direction": "inbound",
  "message_id": "m1",
  "provider": "whatsapp",
  "bridge_id": "whatsapp-main",
  "provider_message_id": "pm1",
  "sender_id": "+919876543210",
  "sender_folder": "919876543210",
  "timestamp_utc": "2026-03-23T05:00:00Z",
  "text": "Hi",
  "attachments": []
}""",
        encoding="utf-8",
    )

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE ChannelInboundMessages (provider TEXT, message_id TEXT, handled INTEGER, UNIQUE(provider, message_id))")
        cur.execute("CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)")
        conn.commit()
    finally:
        conn.close()

    _DummyController.mapped_user_id = ""
    _DummyController.mapped_mobile_user_id = ""
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(root))
    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    service._process_one_inbound("919876543210", msg)

    send_root = root / "send" / "919876543210"
    folders = [p for p in send_root.iterdir() if p.is_dir()]
    assert len(folders) == 1
    text = (folders[0] / "message.txt").read_text(encoding="utf-8")
    assert "you have reached oasis" in text.lower()
    assert "/register" in text


def test_unregistered_new_command_is_ignored(tmp_path) -> None:
    root = tmp_path / "exchange"
    recv = root / "received" / "919876543210"
    msg = recv / "m1"
    msg.mkdir(parents=True, exist_ok=True)
    (msg / "message.json").write_text(
        """{
  "protocol": "das.whatsapp.folder/1.0",
  "direction": "inbound",
  "message_id": "m1",
  "provider": "whatsapp",
  "bridge_id": "whatsapp-main",
  "provider_message_id": "pm1",
  "sender_id": "+919876543210",
  "sender_folder": "919876543210",
  "timestamp_utc": "2026-03-23T05:00:00Z",
  "text": "/new",
  "attachments": []
}""",
        encoding="utf-8",
    )

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE ChannelInboundMessages (provider TEXT, message_id TEXT, handled INTEGER, UNIQUE(provider, message_id))")
        cur.execute("CREATE TABLE ChannelUsers (provider TEXT, channel_user_id TEXT, user_id TEXT, updated_at DATETIME)")
        conn.commit()
    finally:
        conn.close()

    _DummyController.mapped_user_id = ""
    _DummyController.mapped_mobile_user_id = ""
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("sqlite_db_path", str(db_path))
    cda.set_setting("whatsapp_folder_root", str(root))
    service = WhatsAppFolderService(cda=cda, whatsapp_controller=_DummyController())

    service._process_one_inbound("919876543210", msg)

    send_root = root / "send" / "919876543210"
    assert not send_root.exists()
