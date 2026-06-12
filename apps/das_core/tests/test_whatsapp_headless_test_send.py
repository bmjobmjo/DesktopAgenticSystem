from pathlib import Path

from apps.api_gateway.whatsapp_headless_bridge import WhatsAppHeadlessBridgeService


class DummyCDA:
    def __init__(self, base_folder: str) -> None:
        self.settings = {"whatsapp_folder_root": base_folder}

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key: str, value) -> None:
        self.settings[key] = value


def test_headless_send_text_writes_outbound_folder(tmp_path: Path) -> None:
    base = tmp_path / "bridge"
    svc = WhatsAppHeadlessBridgeService(DummyCDA(str(base)))
    result = svc.send_text("917511120971", "hello from headless test")

    assert result["ok"] is True
    out_dir = Path(result["path"])
    assert out_dir.exists()
    assert out_dir.parent.name == "917511120971"
    assert (out_dir / "message.txt").read_text(encoding="utf-8") == "hello from headless test"
