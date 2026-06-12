from __future__ import annotations

import os
import sqlite3
import tempfile

from core.common_data_area import CommonDataArea
from core.db_schema import init_db
from tools.gmail_tools import send_gmail_email
from tools.tool_registry import get_tool, sync_tools_to_db


class _DummySmtp:
    instances = []

    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.login_args = None
        self.sent_message = None
        self.from_addr = None
        self.to_addrs = None
        self.closed = False
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True
        return False

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message, from_addr: str, to_addrs):
        self.sent_message = message
        self.from_addr = from_addr
        self.to_addrs = list(to_addrs)


def test_send_gmail_email_uses_settings_and_sends_message(monkeypatch, tmp_path) -> None:
    import tools.gmail_tools as gmail_tools

    _DummySmtp.instances.clear()
    monkeypatch.setattr(gmail_tools.smtplib, "SMTP_SSL", _DummySmtp)

    attachment = tmp_path / "report.txt"
    attachment.write_text("latest report", encoding="utf-8")

    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("gmail_enabled", True)
    cda.set_setting("gmail_sender_email", "sender@gmail.com")
    cda.set_setting("gmail_sender_name", "OASIS Bot")
    cda.set_setting("gmail_app_password", "app-password-123")
    cda.set_setting("accessible_directories", [str(tmp_path)])

    result = send_gmail_email(
        to=["alice@example.com"],
        subject="Weekly Report",
        body="Please find the latest report attached.",
        cc="manager@example.com",
        bcc=["audit@example.com"],
        attachment_paths=[str(attachment)],
    )

    assert result["success"] is True
    assert result["sender_email"] == "sender@gmail.com"
    assert result["attachment_count"] == 1

    smtp = _DummySmtp.instances[-1]
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 465
    assert smtp.login_args == ("sender@gmail.com", "app-password-123")
    assert smtp.from_addr == "sender@gmail.com"
    assert smtp.to_addrs == ["alice@example.com", "manager@example.com", "audit@example.com"]
    assert smtp.sent_message["Subject"] == "Weekly Report"
    assert smtp.sent_message["From"] == "OASIS Bot <sender@gmail.com>"
    assert smtp.sent_message["To"] == "alice@example.com"
    assert smtp.sent_message["Cc"] == "manager@example.com"


def test_send_gmail_email_requires_configured_credentials() -> None:
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("gmail_enabled", True)

    result = send_gmail_email(
        to="alice@example.com",
        subject="Hello",
        body="World",
    )

    assert result["success"] is False
    assert "gmail_sender_email" in result["error"]


def test_send_gmail_email_requires_enabled_setting() -> None:
    cda = CommonDataArea()
    cda.reset()
    cda.set_setting("gmail_sender_email", "sender@gmail.com")
    cda.set_setting("gmail_app_password", "app-password-123")

    result = send_gmail_email(
        to="alice@example.com",
        subject="Hello",
        body="World",
    )

    assert result["success"] is False
    assert "gmail_enabled" in result["error"]


def test_sync_tools_to_db_registers_send_gmail_email_metadata() -> None:
    cda = CommonDataArea()
    cda.reset()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tools.db")
        cda.set_setting("sqlite_db_path", db_path)
        init_db()
        sync_tools_to_db(cda)

        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT description, input_schema, output_schema, example_call FROM ToolList WHERE name=?",
                ("send_gmail_email",),
            )
            row = cur.fetchone()
        finally:
            conn.close()

        assert row is not None
        description, input_schema, output_schema, example_call = row
        assert "Gmail SMTP" in description
        assert "attachment_paths" in input_schema
        assert "sender email" in output_schema.lower()
        assert "Weekly report" in example_call
        assert get_tool("send_gmail_email") is not None
