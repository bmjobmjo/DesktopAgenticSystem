from pathlib import Path

from apps.api_gateway.whatsapp_headless_bridge import WhatsAppHeadlessBridgeService


class DummyCDA:
    def __init__(self) -> None:
        self.settings: dict[str, object] = {}

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key: str, value) -> None:
        self.settings[key] = value


def test_stop_registration_clears_linked_auth_session(tmp_path: Path) -> None:
    svc = WhatsAppHeadlessBridgeService(DummyCDA())
    svc.headless_dir = tmp_path
    svc.auth_session_dir = tmp_path / "auth_session"
    svc.auth_session_dir.mkdir(parents=True)
    (svc.auth_session_dir / "marker.txt").write_text("linked", encoding="utf-8")
    svc._register_state.update(
        {
            "running": False,
            "phone_number": "919847760326",
            "pairing_code": "DLQ8-4KF9",
            "stage": "linked",
            "last_error": "should be cleared",
        }
    )

    status = svc.stop_registration()

    assert not svc.auth_session_dir.exists()
    assert status["auth_session_exists"] is False
    assert status["register"]["running"] is False
    assert status["register"]["stage"] == "stopped"
    assert status["register"]["pairing_code"] == ""
    assert status["register"]["last_error"] == ""
