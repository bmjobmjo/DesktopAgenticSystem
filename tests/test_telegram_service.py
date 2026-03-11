from __future__ import annotations

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
